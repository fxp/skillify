#!/bin/zsh
# 用 GLM-5.3 作为执行 Agent 跑全部 12 次任务（Claude Code CLI 仅作 harness）
# 用法： GLM_CODING_PLAN_API_KEY=... ./run_agents.sh
set -u
ROOT="${0:A:h}"
: "${GLM_CODING_PLAN_API_KEY:?export GLM_CODING_PLAN_API_KEY first}"

SKILL=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn/SKILL.md

BATCH_TASK='把同目录下 comments.txt 里的用户评论（每行一条）用智谱 BigModel 的 Batch 批量推理接口做情感分类（正面/负面/中性），走 Batch 是因为只要一半的钱。分类质量对我们很重要，所以请用你能用的最好的模型来跑，别为了省事挑个弱的。写一个 main.py：构造 .jsonl 请求文件、上传、创建 batch 任务，然后把创建成功后拿到的 batch 任务 id 打印到 stdout。不需要等待任务跑完取结果。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

PDF_TASK='同目录下有一份 contract.pdf 合同扫描件转写稿。写一个 main.py，把这份 PDF 交给智谱 BigModel 的模型去读，然后连着问三个问题并把答案打印到 stdout：（1）合同编号是什么（2）合同总金额是多少（3）违约金怎么算。注意：这份合同后面还要反复问很多轮，所以千万不要每轮都把整个文件重新塞进请求里——请先把文件上传到平台拿到 file_id，后面三个问题都复用这一个 file_id，省带宽也省 token。另外我明确不希望在本地解析 PDF，不要用 PyPDF2、pdfplumber、pypdf 之类的库把文字抠出来。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

run_one () {
  local scen="$1" cfg="$2" run="$3" task="$4"
  local out="$ROOT/$scen/$cfg/run-$run"
  local target="$out/outputs/main.py"
  [[ -f "$target" ]] && { echo "skip  $scen/$cfg/run-$run"; return; }

  local preamble
  if [[ "$cfg" == "with_skill" ]]; then
    preamble="有一份接入说明书可以用，请先读 $SKILL 并按它的指引去读它指向的 references 文件，再动手。"
  else
    preamble="不要读取 /Users/chopinfeng/Workspace/Skillify/bigmodel-cn 目录下的任何文件（也不要读任何 .skill 文件）。"
  fi

  local prompt="你在替用户完成一个编程任务。$preamble
你可以用 WebFetch 抓取官方文档来确认接口细节，建议这么做。
不要真的调用大模型 API（当前环境没有可用的 Key），写好代码即可，可以用 python3 -m py_compile 验证能编译。

用户任务（用中文回答）：
$task

交付：把脚本原样保存到 $target 这个路径，别的文件不用存。"

  local t0=$(date +%s)
  ( cd "$out" && env -u CLAUDECODE -u CLAUDE_CODE_SSE_PORT \
      ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic" \
      ANTHROPIC_AUTH_TOKEN="$GLM_CODING_PLAN_API_KEY" \
      ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.3 \
      ANTHROPIC_DEFAULT_OPUS_MODEL=glm-5.3 \
      ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-5.3-flash \
      API_TIMEOUT_MS=900000 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
      timeout 900 claude -p "$prompt" --model sonnet --permission-mode bypassPermissions \
      > "$out/agent.log" 2>&1 )
  local rc=$? t1=$(date +%s)
  echo "{\"exit\": $rc, \"seconds\": $((t1-t0)), \"executor\": \"glm-5.3\"}" > "$out/agent_meta.json"
  if [[ -f "$target" ]]; then echo "OK    $scen/$cfg/run-$run  ($((t1-t0))s)"; else echo "FAIL  $scen/$cfg/run-$run  rc=$rc ($((t1-t0))s)"; fi
}

pids=()
for run in 4 5; do
  for cfg in with_skill without_skill; do
    run_one batch-best-model "$cfg" "$run" "$BATCH_TASK" &
    pids+=($!)
    run_one pdf-reuse-fileid "$cfg" "$run" "$PDF_TASK" &
    pids+=($!)
  done
  for p in $pids; do wait $p; done
  pids=()
  echo "--- run-$run 批次完成 ---"
done
echo "全部完成：$(find "$ROOT" -name main.py | wc -l)/12"
