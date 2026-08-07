class ScoreResult {
  score int
  keywords string
  reasoning string
}

function ScoreJob(system_prompt: string, resume: string, job: string) -> ScoreResult {
  client ScoringClient
  prompt #"
    {{ system_prompt }}

    RESUME:
    {{ resume }}

    ---

    JOB POSTING:
    {{ job }}

    {{ ctx.output_format }}
  "#
}

class JudgeResult {
  passed bool
  issues string
}

function JudgeTailoredResume(
  system_prompt: string,
  job_title: string,
  original: string,
  tailored: string,
) -> JudgeResult {
  client JudgeClient
  prompt #"
    {{ system_prompt }}

    JOB TITLE: {{ job_title }}

    ORIGINAL RESUME:
    {{ original }}

    ---

    TAILORED RESUME:
    {{ tailored }}

    Judge this tailored resume:
    {{ ctx.output_format }}
  "#
}
