# quant-super-agent — one command per promise (v1.4)
#
#   make verify        全量测试（170+ 断言，CI 同款）
#   make offense       快车道默认跑（300 日窗，~20s）
#   make offense-full  全窗跑（1210 日，~1 分钟，产出过线候选）
#   make followup      对话式追问（示例：改门槛，零重算）
#   make mem           记忆台账（教训 + 只紧不松检查 + 运行清单）
#   make tour          演示数字再生 + 漂移报警（对 docs/TOUR_NUMBERS.json）
#   make tour-write    用一次真实运行重写演示数字基线
#   make throughput    产能基准：候选/分钟 + 下限门禁（work/throughput/）
#   make badge         重算 tests 徽章端点（docs/badge/tests.json）
#   make readme-render 渲染 README 口径卡（从 docs/STATUS.json）
#   make readme-check  门面检查：禁词 lint + SSOT + 发版冻结
#   make release-readme V=1.4.2  发版：刷新 STATUS、渲染卡、快照、状态页

PY ?= python3

.PHONY: verify offense offense-full followup mem tour tour-write throughput badge readme-render readme-check release-readme

verify:
	$(PY) -m pytest tests/ -q

offense:
	$(PY) examples/run_offense.py --work work/offense

offense-full:
	$(PY) examples/run_offense.py --work work/offense-full --full

followup:
	$(PY) -m qsa.followup --prev work/offense-full "门槛提到 0.05"

mem:
	$(PY) -m qsa.memreport work/offense-full

tour:
	$(PY) tools/regen_tour_numbers.py --work work/offense-full

tour-write:
	$(PY) tools/regen_tour_numbers.py --work work/offense-full --write

throughput:
	$(PY) tools/throughput_bench.py

badge:
	$(PY) tools/write_badge.py

readme-render:
	$(PY) tools/render_readme.py

readme-check:
	$(PY) tools/check_readme.py

release-readme:
	$(PY) tools/release_readme.py $(V)
