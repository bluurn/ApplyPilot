// Provider settings injected at runtime by baml_adapter._setup_env().
// baml_adapter.py mirrors llm.py's provider detection and sets these env vars
// before any BAML call.

// temperature 0.0 — deterministic extraction (selectors, strategy, detail, api judge)
client<llm> DeterministicClient {
  provider "openai"
  options {
    base_url env.BAML_BASE_URL
    api_key env.BAML_API_KEY
    model env.BAML_MODEL
    temperature 0
  }
}

// temperature 0.1 — near-deterministic judge
client<llm> JudgeClient {
  provider "openai"
  options {
    base_url env.BAML_BASE_URL
    api_key env.BAML_API_KEY
    model env.BAML_MODEL
    temperature 0.1
  }
}

// temperature 0.2 — scoring
client<llm> ScoringClient {
  provider "openai"
  options {
    base_url env.BAML_BASE_URL
    api_key env.BAML_API_KEY
    model env.BAML_MODEL
    temperature 0.2
  }
}

// temperature 0.4 — tailoring
client<llm> TailoringClient {
  provider "openai"
  options {
    base_url env.BAML_BASE_URL
    api_key env.BAML_API_KEY
    model env.BAML_MODEL
    temperature 0.4
  }
}

// temperature 0.7 — cover letter (more creative)
client<llm> CreativeClient {
  provider "openai"
  options {
    base_url env.BAML_BASE_URL
    api_key env.BAML_API_KEY
    model env.BAML_MODEL
    temperature 0.7
  }
}
