-- hub_translator：8 个 trigger 型 lua 翻译器的统一入口（v1.2.0 批次 2）
--
-- 背景：librime 的 Translator 基类不做 tag 过滤，engine 里每多注册一个
-- lua_translator，每个段查询都要多付一次 C++ 层固定入口开销（批次 1 实测
-- 组删 10 个 trigger 翻译器 Δ≈+2.96 ms/键，其中入口开销占绝对大头）。
-- 本模块把 8 个低频 trigger 翻译器收进一个入口，按原注册序逐模块判定
-- 触发条件做 O(1) 分发；普通拼音输入所有判定皆假、零调用。
--
-- 路由（func 内按原注册序展开，改造前 schema translators 顺序；
-- 各模块判定独立、不互斥，重叠输入按序多模块都调，与 8 注册等价）：
--   1 version_display：env.hub_exact 命中（/sanhe）
--   2 set_schema：env.hub_exact 命中（/pinyin /flypy）
--   3 set_profile：env.hub_exact 命中（/fast /balance /full）
--     （1-3 共用 env.hub_exact[input] → 模块函数 表，三个模块命令键天然互斥）
--   4 shijian：first=="N"（N 前缀日期/日期差）或任一 shijian_keys 前缀
--     （默认 "/" "o"）命中 → shijian 宽门
--   5 unicode_conversion.T：seg:has_tag("unicode") 或 first=="U"
--   6 number_conversion：seg:has_tag("number") 或 first=="R"
--   7 super_calculator：seg:has_tag("calculator") 或 first=="V"/"v"
--     （小写 v 由门内裁决：纯拼音形态零副作用拒绝，表达式形态收进计算器；
--      裸 v+单数字已被 schema recognizer 打 calculator tag，走 tag 分支进
--      计算器，hub 不在此拦截）
--   8 random_tools：env.hub_random_cmds[input] 命中（命令集来自 random_tools/*
--      配置，init 时读入；如自定义命令 R1234，第 6 步 number 与第 8 步
--      random 按序都会执行）
--   其余（普通拼音、数字句等）→ 全部判定皆假，不进任何模块
--
-- 说明：
--   * hub_exact 只放头三位命令，random_tools 命令单独存 hub_random_cmds
--     （命令→true 集合表）：同键冲突时按原注册序各调各的，且不存在
--     「单值表被后写覆盖」问题。
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

-- 路由状态挂在 env 上（hub_shijian_keys / hub_exact / hub_random_cmds）：
-- 多方案或多会话 env 共存时（如 sanhe 与 sanhe_reverse 同时注册 hub），
-- 后初始化者不再覆盖前者的模块级表，各 env 路由互不影响。
-- 随 init 填充，重新部署即重建。

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

    -- 精确命令表（O(1) 命中）：头三位模块的命令键天然互斥，共用一张
    -- 命令→模块函数表；random_tools 命令不放入此表（见下 hub_random_cmds）
    env.hub_exact = {
        ["/sanhe"] = version_display,
        ["/pinyin"] = set_schema,
        ["/flypy"] = set_schema,
        ["/fast"] = set_profile,
        ["/balance"] = set_profile,
        ["/full"] = set_profile,
    }

    -- random_tools 命令集合（命令→true）：按原注册序在最后一步判定，
    -- 与头三位命令表分离，同键冲突时按原注册序各调各的
    env.hub_random_cmds = {}
    if env.uuid_code then env.hub_random_cmds[env.uuid_code] = true end
    if env.uuid7_code then env.hub_random_cmds[env.uuid7_code] = true end
    if env.ulid_code then env.hub_random_cmds[env.ulid_code] = true end
    if env.password_code then env.hub_random_cmds[env.password_code] = true end
    if env.password_special_code then env.hub_random_cmds[env.password_special_code] = true end
end

local function fini(env)
    random_tools.fini(env)
    unicode_conversion.T.fini(env)
    -- 清理 hub 路由状态（oracle 建议：随 fini 释放，避免悬挂引用）
    env.hub_exact = nil
    env.hub_random_cmds = nil
    env.hub_shijian_keys = nil
end

local function func(input, seg, env)
    local first = input:sub(1, 1)
    local shijian_keys = env.hub_shijian_keys or {}

    -- 1-3. 头三位精确命令模块（互斥）：命中即调对应模块，不提前拦截
    -- 后续模块（shijian 宽门等仍按原注册序独立判定）
    local exact = (env.hub_exact or {})[input]
    if exact then exact(input, seg, env) end

    -- 4. shijian：N 前缀日期/日期差，或 shijian_keys（默认 "/" "o"）宽门
    if first == "N" then
        shijian(input, seg, env)
    else
        for _, key in ipairs(shijian_keys) do
            if input:sub(1, #key) == key then
                shijian(input, seg, env)
                break
            end
        end
    end

    -- 5. unicode_conversion.T：unicode tag 或 U 前缀
    if seg:has_tag("unicode") or first == "U" then
        unicode_conversion.T.func(input, seg, env)
    end

    -- 6. number_conversion：number tag 或 R 前缀
    if seg:has_tag("number") or first == "R" then
        number_conversion(input, seg, env)
    end

    -- 7. super_calculator：calculator tag 或 V/v 前缀（门内裁决小写形态）
    if seg:has_tag("calculator") or first == "V" or first == "v" then
        super_calculator.func(input, seg, env)
    end

    -- 8. random_tools：命令集合命中（按原注册序最后判定，与前缀模块可重叠）
    if (env.hub_random_cmds or {})[input] then
        random_tools.func(input, seg, env)
    end
end

return { init = init, func = func, fini = fini }
