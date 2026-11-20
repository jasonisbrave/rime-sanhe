-- hub_translator：8 个 trigger 型 lua 翻译器的统一入口（v1.2.0 批次 2）
--
-- 背景：librime 的 Translator 基类不做 tag 过滤，engine 里每多注册一个
-- lua_translator，每个段查询都要多付一次 C++ 层固定入口开销（批次 1 实测
-- 组删 10 个 trigger 翻译器 Δ≈+2.96 ms/键，其中入口开销占绝对大头）。
-- 本模块把 8 个低频 trigger 翻译器收进一个入口，按输入形态做 O(1) 分发，
-- 普通拼音输入一个模块都不进。
--
-- 路由表（func 内的判定顺序，即调用优先级）：
--   1. 精确命令表 env.hub_exact（/sanhe /pinyin /flypy /fast /balance /full
--      + random_tools/* 配置的自定义命令）→ 对应模块；若输入同时落在
--      shijian 宽门内则照旧「精确模块 + shijian」都调，保 segment.tags
--      与候选顺序和改造前一致
--   2. tag 路由（自定义 recognizer 前缀兜底）：段带 calculator tag →
--      super_calculator；number tag → number_conversion；unicode tag →
--      unicode_conversion.T（无论首字母是什么，自定义前缀也进）
--   3. 默认前缀快捷路径：V/v → super_calculator（小写 v 由门内裁决）、
--      R → number_conversion、U → unicode_conversion.T、N → shijian
--   4. shijian 宽门兜底：shijian_keys 前缀（默认 "/" "o"）引导的输入
--      → shijian（斜杠/字母 o 引导的一切输入，与改造前一致）
--   其余（普通拼音、数字句等）→ 全部跳过，不进任何模块
--
-- 说明：
--   * v 前缀直进 super_calculator：双拼下 v 是合法声母（zh），纯拼音形态
--     （vsj 等）在门内被拒绝、零副作用，候选原样留给拼音翻译器；而裸 v+单
--     数字（v1）已被 schema 的 recognizer pattern 打上 calculator tag，
--     走第 2 级 tag 路由进计算器（选词/声调让位），hub 不在此拦截。
--   * 精确命令优先于前缀：random_tools 自定义命令若以 V/R/U/v 开头，
--     不会被前缀分支独占，仍先命中精确表。
--   * set_schema/set_profile 的版本判断、文件读写全部保留在各自模块内，
--     hub 只做分发，不改任何目标模块源码。

local version_display = require("sanhe/version_display")
local set_schema = require("sanhe/set_schema")
local set_profile = require("sanhe/set_profile")
local shijian = require("sanhe/shijian")
local number_conversion = require("sanhe/number_conversion")
local random_tools = require("sanhe/random_tools")
local unicode_conversion = require("sanhe/unicode_conversion")
local super_calculator = require("sanhe/super_calculator")

-- 路由状态挂在 env 上（hub_shijian_keys / hub_exact）：多方案或多会话 env
-- 共存时（如 sanhe 与 sanhe_reverse 同时注册 hub），后初始化者不再覆盖
-- 前者的模块级表，各 env 路由互不影响。随 init 填充，重新部署即重建。

-- 与 shijian.lua 相同的 key_binder/shijian_keys 读取逻辑
local function read_shijian_keys(config)
    local keys = {}
    local list = config:get_list("key_binder/shijian_keys")
    if list then
        for i = 0, list.size - 1 do
            local value = list:get_value_at(i).value
            if type(value) == "string" and value ~= "" then
                keys[#keys + 1] = value
            end
        end
    end
    return keys
end

local function init(env)
    -- random_tools：把 random_tools/* 配置（触发命令/密码长度/字符集）读进 env
    random_tools.init(env)
    -- super_calculator：解析 recognizer/patterns/calculator 得到 T.prefix（默认 V）
    super_calculator.init(env)
    -- unicode_conversion.T：建立反查 memory（T.func 的词典转换候选依赖它）
    unicode_conversion.T.init(env)

    env.hub_shijian_keys = read_shijian_keys(env.engine.schema.config)

    -- 精确命令表（O(1) 命中；random_tools 的触发命令以配置为准）
    env.hub_exact = {
        ["/sanhe"] = version_display,
        ["/pinyin"] = set_schema,
        ["/flypy"] = set_schema,
        ["/fast"] = set_profile,
        ["/balance"] = set_profile,
        ["/full"] = set_profile,
    }
    if env.uuid_code then env.hub_exact[env.uuid_code] = random_tools.func end
    if env.uuid7_code then env.hub_exact[env.uuid7_code] = random_tools.func end
    if env.ulid_code then env.hub_exact[env.ulid_code] = random_tools.func end
    if env.password_code then env.hub_exact[env.password_code] = random_tools.func end
    if env.password_special_code then env.hub_exact[env.password_special_code] = random_tools.func end
end

local function fini(env)
    random_tools.fini(env)
    unicode_conversion.T.fini(env)
end

local function func(input, seg, env)
    local first = input:sub(1, 1)
    local shijian_keys = env.hub_shijian_keys or {}
    local exact = (env.hub_exact or {})[input]

    -- 1. 精确命令表优先（含 random_tools 自定义命令）：命中即调对应模块，
    -- 不被下方 V/R/U/v 前缀分支独占；同时落在 shijian 宽门内的照旧
    -- 「精确模块 + shijian」都调，保 segment.tags 与候选顺序和改造前一致
    if exact then
        exact(input, seg, env)
        for _, key in ipairs(shijian_keys) do
            if input:sub(1, #key) == key then
                return shijian(input, seg, env)
            end
        end
        return
    end

    -- 2. tag 路由：段被 recognizer 打上 calculator/number/unicode tag 时直发
    -- 对应模块（自定义前缀，如把计算器引导改成 C 前缀，首字母不在默认表
    -- 也能进）；calculator 的 tag 判定由 schema 的 recognizer pattern 负责
    if seg:has_tag("calculator") then
        return super_calculator.func(input, seg, env)
    end
    if seg:has_tag("number") then
        return number_conversion(input, seg, env)
    end
    if seg:has_tag("unicode") then
        return unicode_conversion.T.func(input, seg, env)
    end

    -- 3. 默认前缀快捷路径（与历史触发面一致；小写 v 由 super_calculator
    -- 门内裁决：纯拼音形态零副作用拒绝，表达式形态收进计算器）
    if first == "V" or first == "v" then
        return super_calculator.func(input, seg, env)
    end
    if first == "R" then
        return number_conversion(input, seg, env)
    end
    if first == "U" then
        return unicode_conversion.T.func(input, seg, env)
    end
    if first == "N" then
        -- shijian 的 N 前缀日期/日期差分支；N 不匹配 shijian_keys，内部直通
        return shijian(input, seg, env)
    end

    -- 4. shijian 宽门兜底：shijian_keys 前缀（默认 "/" "o"）引导的输入全量
    -- 放行，与改造前「shijian 每个段都被调用」的行为保持一致
    for _, key in ipairs(shijian_keys) do
        if input:sub(1, #key) == key then
            return shijian(input, seg, env)
        end
    end
end

return { init = init, func = func, fini = fini }
