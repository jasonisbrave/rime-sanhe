--[[
三合五笔召唤模块（beta）
功能：在三合拼音方案中输入 /w + 五笔编码（如 /wvbg），直接召唤五笔86候选。
      候选注释显示完整编码，边打边学码；支持前缀补全（/wvb 列出 vb 开头编码）。
实现：参照 super_english 的 Component.TableTranslator 挂载模式，
      绑定 wubi86 词典，纯增量功能，不影响拼音流与 /flypy 切换。
]]

local match = string.match
local format = string.format

local DEFAULT_TRIGGER = "/w"
local DEFAULT_MAX_CANDIDATES = 30

local T = {}

function T.init(env)
    env.trigger = DEFAULT_TRIGGER
    env.max_candidates = DEFAULT_MAX_CANDIDATES

    local config = env.engine and env.engine.schema and env.engine.schema.config
    if config then
        local trigger = config:get_string("sanhe_wubi/trigger")
        if trigger and #trigger > 0 then
            env.trigger = trigger
        end
        local limit = config:get_int("sanhe_wubi/max_candidates")
        if limit and limit > 0 then
            env.max_candidates = limit
        end
    end

    -- 转义触发前缀中的魔法字符，便于拼接 Lua 匹配模式
    env.trigger_pattern = "^" .. env.trigger:gsub("([%%%^%$%(%)%.%[%]%*%+%-%?])", "%%%1") .. "([a-z]*)$"

    if not Component or type(Component.TableTranslator) ~= "function" then
        return
    end

    env.wubi_translator = Component.TableTranslator(env.engine, "sanhe_wubi", "table_translator")
end

function T.func(input, seg, env)
    if not env.wubi_translator then
        return
    end

    local ctx = env.engine.context
    if ctx:get_option("ascii_mode") then
        return
    end

    local code = match(input, env.trigger_pattern)
    if not code then
        return
    end

    -- 仅输入前缀：给出用法提示
    if code == "" then
        local tip = Candidate("sanhe_wubi", seg.start, seg._end,
            format("五笔召唤：接着输入编码，如 %svbg", env.trigger), "〔beta〕")
        tip.preedit = input
        tip.quality = 2
        yield(tip)
        return
    end

    local translation = env.wubi_translator:query(code, seg)
    if not translation then
        return
    end

    local emitted = 0
    for cand in translation:iter() do
        -- cand.preedit 为该候选对应的完整五笔编码，显示为注释便于学习
        local item = Candidate("sanhe_wubi", seg.start, seg._end,
            cand.text, cand.preedit or code)
        item.preedit = input
        item.quality = 2
        yield(item)

        emitted = emitted + 1
        if emitted >= env.max_candidates then
            break
        end
    end
end

function T.fini(env)
    if env.wubi_translator then
        env.wubi_translator:disconnect()
        env.wubi_translator = nil
    end
end

return T
