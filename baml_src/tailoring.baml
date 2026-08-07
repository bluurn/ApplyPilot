class ExperienceDraft {
  header string
  subtitle string?
  bullets string[]
}

class ProjectDraft {
  header string
  subtitle string?
  bullets string[]
}

class TailoredDraft {
  title string
  summary string
  skills map<string, string>
  experience ExperienceDraft[]
  projects ProjectDraft[]
  education string
}

function RewriteTailoredResume(
  system_prompt: string,
  resume: string,
  job: string,
) -> TailoredDraft {
  client TailoringClient
  prompt #"
    {{ system_prompt }}

    ORIGINAL RESUME:
    {{ resume }}

    ---

    TARGET JOB:
    {{ job }}

    Return the JSON:
    {{ ctx.output_format }}
  "#
}
