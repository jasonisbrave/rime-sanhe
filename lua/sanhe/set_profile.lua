local sanhe = require("sanhe/sanhe")

-- 输入 '/fast' '/balance' '/full' 切换性能档位，改写用户目录 sanhe.custom.yaml 后需重新部署
-- /fast    极速档：关闭补全、降低注释数量
-- /balance 均衡档：仅降低注释数量
-- /full    标准档：移除维护块，恢复默认

local MAIN_FILE = "sanhe.custom.yaml"
local MARK_BEGIN = "# >>> 性能档位"
local MARK_END = "# <<< 性能档位 <<<"

local PROFILES = {
    ["/fast"] = {
        name = "极速档",
        lines = {
            "  translator/enable_completion: false",
            "  translator/spelling_hints: 6",
            "  sanhe_english/enable_completion: false",
            "  sanhe_mixedcode/enable_completion: false",
        },
    },
    ["/balance"] = {
        name = "均衡档",
        lines = {
            "  translator/spelling_hints: 15",
        },
    },
}

local function copy_file(src, dest)
    local fi = io.open(src, "rb")
    if not fi then
        return false
    end

    local content = fi:read("*a")
    fi:close()

    local fo = io.open(dest, "wb")
    if not fo then
        return false
    end

    fo:write(content)
    fo:close()
    return true
end

local function file_exists(path)
    local f = io.open(path, "r")
    if f then
        f:close()
        return true
    end
    return false
end

-- 是否存在顶层 patch: 映射键（行首无缩进）。追加档位键前必须确认，否则会生成无效 YAML
local function has_top_level_patch(lines)
    for _, line in ipairs(lines) do
        if line:match("^patch:%s*$") then
            return true
        end
    end
    return false
end

-- 移除旧性能档位块（从标记首行到标记末行，含两端）
-- 返回：新行表、是否移除过块、块是否未闭合（有 # >>> 无 # <<<，视为损坏）
local function strip_block(lines)
    local out = {}
    local in_block = false
    local removed = false

    for _, line in ipairs(lines) do
        if not in_block and line:find(MARK_BEGIN, 1, true) == 1 then
            in_block = true
            removed = true
        elseif in_block then
            if line:find(MARK_END, 1, true) == 1 then
                in_block = false
            end
        else
            table.insert(out, line)
        end
    end

    return out, removed, in_block
end

local function build_block(profile)
    local lines = { MARK_BEGIN .. "（/fast /balance /full 自动维护，手动修改会被覆盖）>>>" }
    for _, l in ipairs(profile.lines) do
        table.insert(lines, l)
    end
    table.insert(lines, MARK_END)
    return lines
end

-- 返回 status：
--   ok           已写入
--   nochange     /full 无块，无需改动
--   err_read     读文件失败
--   err_write    写文件失败
--   err_no_patch 缺少顶层 patch: 段，未修改（避免生成无效 YAML）
--   err_unclosed 档位标记块未闭合，未修改（避免误删块后内容）
local function apply_profile(dest, input)
    local f = io.open(dest, "r")
    if not f then
        return "err_read"
    end

    local content = f:read("*a")
    f:close()

    local eol = content:find("\r\n", 1, true) and "\r\n" or "\n"
    local ended_with_eol = content:sub(-1) == "\n"

    -- 按行拆分（保留行尾空行，确保块移除后可逐字节还原）；行内容不含换行符
    local lines = {}
    for line in content:gmatch("(.-)\n") do
        if eol == "\r\n" then
            line = line:gsub("\r$", "")
        end
        table.insert(lines, line)
    end
    -- 捕获无换行结尾的末尾行（若有）
    local tail = content:match("([^\n]*)$")
    if tail ~= "" then
        if eol == "\r\n" then
            tail = tail:gsub("\r$", "")
        end
        table.insert(lines, tail)
    end

    local stripped, removed, unclosed = strip_block(lines)
    if unclosed then
        return "err_unclosed"
    end

    if input == "/full" then
        if not removed then
            return "nochange"
        end
    else
        if not has_top_level_patch(stripped) then
            return "err_no_patch"
        end

        -- 块追加到文件末尾（仍在 patch: 映射上下文内）
        local profile = PROFILES[input]
        local block = build_block(profile)
        for _, l in ipairs(block) do
            table.insert(stripped, l)
        end
    end

    local new_content = table.concat(stripped, eol)
    if ended_with_eol then
        new_content = new_content .. eol
    end

    f = io.open(dest, "w")
    if not f then
        return "err_write"
    end

    f:write(new_content)
    f:close()
    return "ok"
end

local function translator(input, seg, env)
    if input ~= "/fast" and input ~= "/balance" and input ~= "/full" then
        return
    end

    local user_dir = rime_api.get_user_data_dir()
    local shared_dir = rime_api.get_shared_data_dir()
    local dest = user_dir .. "/" .. MAIN_FILE

    if not file_exists(dest) then
        -- /full 且配置文件不存在：本就是默认配置，不复制模板、不产生任何写入
        if input == "/full" then
            yield(Candidate("switch", seg.start, seg._end,
                "当前已是标准档（默认配置），无需切换", ""))
            return
        end

        local src = shared_dir .. "/custom/" .. MAIN_FILE
        if not file_exists(src) then
            src = user_dir .. "/custom/" .. MAIN_FILE
        end

        if file_exists(src) then
            copy_file(src, dest)
        else
            yield(Candidate("switch", seg.start, seg._end,
                "未找到切换模板（custom/" .. MAIN_FILE .. "），配置未写入，请检查安装是否完整", ""))
            return
        end
    end

    local status = apply_profile(dest, input)

    if status == "err_read" or status == "err_write" then
        yield(Candidate("switch", seg.start, seg._end,
            "读写 " .. MAIN_FILE .. " 失败，请检查文件权限", ""))
        return
    end

    if status == "err_no_patch" then
        yield(Candidate("switch", seg.start, seg._end,
            MAIN_FILE .. " 缺少顶层 patch: 段，为避免生成无效配置未做修改，请手动检查", ""))
        return
    end

    if status == "err_unclosed" then
        yield(Candidate("switch", seg.start, seg._end,
            "检测到未闭合的档位标记（有 # >>> 无 # <<<），为避免丢失配置已中止，请手动修复 " .. MAIN_FILE, ""))
        return
    end

    if status == "nochange" then
        yield(Candidate("switch", seg.start, seg._end,
            "当前已是标准档（默认配置），无需切换", ""))
        return
    end

    local msg
    if input == "/fast" then
        msg = "已切换到〔极速档〕，请重新部署生效"
    elseif input == "/balance" then
        msg = "已切换到〔均衡档〕，请重新部署生效"
    else
        msg = "已恢复〔标准档〕，请重新部署生效"
    end

    yield(Candidate("switch", seg.start, seg._end, msg, ""))
end

return translator
