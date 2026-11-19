# 更新日志

本项目的显著变更记录在此。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本语义遵循 SemVer。

## [1.1.0] - 2026-11-19
### 新增
- 性能档位切换：/fast /balance /full（改写 sanhe.custom.yaml，需重新部署）
- 延迟基准测试工具 tools/bench/（基于小狼毫 rime.dll 的真实引擎测量）
- GitHub Actions 部署验证 CI 与发布打包脚本 tools/release/package.py
### 变更
- 五笔召唤由 beta 转正
### 文档
- 新增 docs/voice-2.0-research.md（v2.0 语音输入立项调研，v2.0 维持调研阶段）

## [1.1.0-beta1] - 2026-09-13
### 新增
- 五笔召唤（beta）：拼音方案中 /w+五笔编码 直接出候选，注释显示编码

## [1.0.0] - 2026-09-13
### 新增
- 基于万象拼音内核精简的首个版本：全拼/小鹤双拼/五笔86 三方案
