local sanhe = require("sanhe/sanhe")

--输入'/sanhe'，显示三合输入法版本与来源信息
local function translator(input, seg, env)
    if input == "/sanhe" then
        yield(Candidate("version", seg.start, seg._end, "三合输入法 v" .. sanhe.version, ""))

        yield(Candidate("upstream", seg.start, seg._end,
            "上游: https://github.com/amzxyz/rime-wanxiang", "〔万象〕"))

        yield(Candidate("doc", seg.start, seg._end,
            "全拼 /pinyin · 小鹤双拼 /flypy · 五笔86见状态面板", "〔帮助〕"))
    end
end

return translator
