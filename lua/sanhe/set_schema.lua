local sanhe = require("sanhe/sanhe")

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

local function get_scheme_info(env)
    local schema_id = env.engine.schema.schema_id or ""

    if schema_id == "sanhe_pro" then
        return "pro", "sanhe_pro.custom.yaml"
    elseif schema_id == "sanhe_lite" then
        return "lite", "sanhe_lite.custom.yaml"
    elseif schema_id == "sanhe" then
        return "base", "sanhe.custom.yaml"
    end

    return nil, nil
end

local function replace_schema(file_path, target_schema, profile)
    local f = io.open(file_path, "r")
    if not f then
        return false
    end

    local content = f:read("*a")
    f:close()

    if file_path:find("sanhe_reverse", 1, true) then
        content = content:gsub(
            "([%s]*__include:%s*sanhe_algebra:/reverse/)%S+",
            "%1" .. target_schema
        )
    elseif file_path:find("sanhe_mixedcode", 1, true) then
        content = content:gsub(
            "([%s]*__patch:%s*sanhe_algebra:/mixed/)%S+",
            "%1" .. target_schema
        )
    elseif file_path:find("sanhe_english", 1, true) then
        content = content:gsub(
            "([%s]*__patch:%s*sanhe_algebra:/english/)%S+",
            "%1" .. target_schema
        )
    elseif file_path:find("sanhe", 1, true)
        and file_path:find(".custom", 1, true)
    then
        content = content:gsub(
            "([%s%-]*sanhe_algebra:/" .. profile .. "/)%S+",
            "%1" .. target_schema,
            1
        )
    end

    f = io.open(file_path, "w")
    if not f then
        return false
    end

    f:write(content)
    f:close()
    return true
end

local function translator(input, seg, env)
    local profile, main_file = get_scheme_info(env)
    if not profile then
        return
    end


    local schema_map = {
        ["/pinyin"]  = "全拼",
        ["/flypy"]   = "小鹤双拼",
    }

    local target_schema = schema_map[input]
    if not target_schema then
        return
    end

    local user_dir = rime_api.get_user_data_dir()
    local shared_dir = rime_api.get_shared_data_dir()
    local dest_main = user_dir .. "/" .. main_file
    local main_exists = file_exists(dest_main)

    local files = {
        "sanhe_mixedcode.custom.yaml",
        "sanhe_reverse.custom.yaml",
        "sanhe_english.custom.yaml",
        main_file,
    }

    for _, name in ipairs(files) do
        local dest = user_dir .. "/" .. name

        if name == main_file and main_exists then
            replace_schema(dest, target_schema, profile)
        else
            local src = shared_dir .. "/custom/" .. name
            if not file_exists(src) then
                src = user_dir .. "/custom/" .. name
            end

            if file_exists(src) and copy_file(src, dest) then
                replace_schema(dest, target_schema, profile)
            end
        end
    end

    local msg = main_exists
        and ("检测到专属配置，已切换到〔" .. target_schema .. "〕，请手动重新部署")
        or ("已从系统目录构建配置并切换到〔" .. target_schema .. "〕，请手动重新部署")

    yield(Candidate("switch", seg.start, seg._end, msg, ""))
end

return translator
