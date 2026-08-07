class StrategyExtraction {
  url_pattern string?
  items_path string?
  title string?
  salary string?
  description string?
  location string?
  url string?
}

class StrategyResult {
  strategy string
  reasoning string
  extraction StrategyExtraction
}

function SelectStrategy(system_prompt: string, briefing: string) -> StrategyResult {
  client DeterministicClient
  prompt #"
    {{ system_prompt }}

    INTELLIGENCE BRIEFING:
    {{ briefing }}

    {{ ctx.output_format }}
  "#
}

class SelectorResult {
  job_card string?
  title string?
  salary string?
  description string?
  location string?
  url string?
  error string?
}

function GenerateSelectors(system_prompt: string, page_html: string) -> SelectorResult {
  client DeterministicClient
  prompt #"
    {{ system_prompt }}

    PAGE HTML:
    {{ page_html }}

    {{ ctx.output_format }}
  "#
}

class RelevanceResult {
  relevant bool
  reason string
}

function JudgeApiResponse(system_prompt: string, api_summary: string) -> RelevanceResult {
  client DeterministicClient
  prompt #"
    {{ system_prompt }}

    {{ api_summary }}

    {{ ctx.output_format }}
  "#
}
