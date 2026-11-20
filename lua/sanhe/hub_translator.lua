-- hub_translator：8 个 trigger 型 lua 翻译器的统一入口（v1.2.0 批次 2）
--
-- 背景：librime 的 Translator 基类不做 tag 过滤，engine 里每多注册一个
-- lua_translator，每个段查询都要多付一次 C++ 层固定入口开销（批次 1 实测
-- 组删 10 个 trigger 翻译器 Δ≈+2.96 ms/键，其中入口开销占绝对大头）。
-- 本模块把 8 个低频 trigger 翻译器收进一个入口，按输入形态做 O(1) 分发，
-- 普通拼音输入一个模块都不进。
--
-- 路由表（输入形态 → 调用的模块，顺序即调用顺序）：
--   "/sanhe"                     → version_display + shijian
--   "/pinyin" "/flypy"           → set_schema + shijian
--   "/fast" "/balance" "/full"   → set_profile + shijian
--   "/uuid" "/uuidq" "/ulid" "/mima" "/mimas"
--                                → random_tools + shijian（命令来自 random_tools/* 配置）
--   "V..."（V 前缀）             → super_calculator
--   "v..."（小写 v 表达式形态）   → super_calculator（门内裁决：v1+2*3 收，
--                                  vsj/v1 等双拼拼音形态拒绝，留给拼音翻译器）
--   "R..."（R 前缀）             → number_conversion
--   "U..."（U 前缀，或段带 unicode tag）
--                                → unicode_conversion.T（P 处理器仍单独注册，不动）
--   "N..."（N 前缀日期/日期差）   → shijian
--   "<shijian_keys 前缀>..."（默认 "/" "o"，余下非空）
--                                → shijian（宽门兜底：斜杠/字母 o 引导的一切输入）
--   其余（普通拼音、数字句等）   → 全部跳过，不进任何模块
--
-- 说明：
--   * 精确命令（/sanhe 等）同时也落在 shijian 的宽门内。原注册下 shijian
--     本来就会被调用（加/减 shijian tag，净效果为零，不出候选），为保持
--     segment.tags 与候选产生顺序完全一致，这里保守地「精确模块 + shijian」
--     都调；代价只是宽门内输入多一次 lua 调用，普通输入不受影响。
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

-- 模块级路由状态：随 init 填充（配置不动不改，重新部署即重建）
local SHIJIAN_KEYS = {}   -- key_binder/shijian_keys（与 shijian.lua 读同一配置）
local EXACT = {}          -- 精确命令表：input -> translator 函数

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

    SHIJIAN_KEYS = read_shijian_keys(env.engine.schema.config)

    -- 精确命令表（O(1) 命中；random_tools 的触发命令以配置为准）
    EXACT = {
        ["/sanhe"] = version_display,
        ["/pinyin"] = set_schema,
        ["/flypy"] = set_schema,
        ["/fast"] = set_profile,
        ["/balance"] = set_profile,
        ["/full"] = set_profile,
    }
    if env.uuid_code then EXACT[env.uuid_code] = random_tools.func end
    if env.uuid7_code then EXACT[env.uuid7_code] = random_tools.func end
    if env.ulid_code then EXACT[env.ulid_code] = random_tools.func end
    if env.password_code then EXACT[env.password_code] = random_tools.func end
    if env.password_special_code then EXACT[env.password_special_code] = random_tools.func end
end

local function fini(env)
    random_tools.fini(env)
    unicode_conversion.T.fini(env)
end

local function func(input, seg, env)
    local first = input:sub(1, 1)

    -- V/v 前缀：大写直进；小写仅「表达式形态」由 super_calculator 门内裁决放行
    -- （双拼下 v 是合法声母 zh，v1+2*3 之类绝不可能是双拼码；纯拼音形态
    --  如 vsj、v1 在门内被拒绝，候选原样留给拼音翻译器）
    if first == "V" or first == "v" then
        return super_calculator.func(input, seg, env)
    end
    if first == "R" then
        return number_conversion(input, seg, env)
    end
    if first == "U" or seg:has_tag("unicode") then
        return unicode_conversion.T.func(input, seg, env)
    end
    if first == "N" then
        -- shijian 的 N 前缀日期/日期差分支；N 不匹配 shijian_keys，内部直通
        local exact = EXACT[input]
        if exact then exact(input, seg, env) end
        return shijian(input, seg, env)
    end

    -- shijian 宽门：shijian_keys 前缀（默认 "/" "o"）引导的输入全量放行，
    -- 与改造前「shijian 每个段都被调用」的行为保持一致（tag 增减、提示清零）
    for _, key in ipairs(SHIJIAN_KEYS) do
        if input:sub(1, #key) == key then
            local exact = EXACT[input]
            if exact then exact(input, seg, env) end
            return shijian(input, seg, env)
        end
    end

    -- 宽门之外仍有精确命中时兜底（当前配置下不存在此类命令，防御配置改动）
    local exact = EXACT[input]
    if exact then
        return exact(input, seg, env)
    end
end

return { init = init, func = func, fini = fini }
