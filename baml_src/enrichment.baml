class DetailResult {
  full_description string?
  application_url string?
}

function ExtractDetail(system_prompt: string, content: string) -> DetailResult {
  client DeterministicClient
  prompt #"
    {{ system_prompt }}

    HTML:
    {{ content }}

    {{ ctx.output_format }}
  "#
}
