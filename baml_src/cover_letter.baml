// Cover letter is plain text — return as string so BAML doesn't inject
// JSON schema instructions that would corrupt the letter format.
function GenerateCoverLetter(
  system_prompt: string,
  resume: string,
  job: string,
) -> string {
  client CreativeClient
  prompt #"
    {{ system_prompt }}

    RESUME:
    {{ resume }}

    ---

    TARGET JOB:
    {{ job }}

    Write the cover letter:
  "#
}
