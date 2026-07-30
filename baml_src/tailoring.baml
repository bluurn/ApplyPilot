class ExperienceDraft {
  header string
  subtitle string
  bullets string[]
}

class ProjectDraft {
  header string
  subtitle string
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

client<llm> TailoringClient {
  provider "openai"
  options {
    model "gpt-4o-mini"
    temperature 0
  }
}

function RewriteTailoredResume(
  original_resume string,
  target_job string,
  fixed_experience string,
  fixed_skills string
) -> TailoredDraft {
  client TailoringClient
  prompt #"
    Rewrite only the supplied fixed resume content for the target job.

    The experience entries and skills are fixed by the calling application.
    Do not add, remove, rename, or reorder them. Rewrite only the summary and
    bullet wording while preserving every factual claim, employer, date,
    technology, and metric.

    FIXED EXPERIENCE:
    {{ fixed_experience }}

    FIXED SKILLS:
    {{ fixed_skills }}

    ORIGINAL RESUME:
    {{ original_resume }}

    TARGET JOB:
    {{ target_job }}
  "#
}
