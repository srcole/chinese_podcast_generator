# News podcast brief

Use this brief when asked to research and prepare a news podcast. A request to
"make" or "generate" a podcast means preparing the text files, not rendering
audio. Read the Amendments section on every request and apply its suggestions.
Explicit instructions in the current request take precedence, followed by
Amendments, then the defaults below. If amendments conflict, use the later entry.

## Default scope

- Timeframe: the previous 48 hours, measured from the time of the request. Record
  the exact date range and timezone in `sources.md`, not in the spoken introduction;
  use Europe/London unless told otherwise.
- Length: approximately 15 minutes for one complete Chinese-only narration at
  the configured `rates.chinese` speed. This is not the combined episode length:
  English, vocabulary, and repeated Chinese sections add listening time.
- Eligible topics: China, USA, tech, business, AI, neuroscience, and major
  international news.
- If the request specifies topics, select from those. Otherwise choose the most
  significant and interesting stories across the eligible topics. There is no
  requirement to include every category; avoid covering the same story twice
  when categories overlap.

## Research and editorial approach

- Research current reporting rather than relying on remembered news. Prefer
  reliable reporting and primary sources, and cross-check major claims where
  practical.
- Check publication dates against event dates during research. Include recent
  developments within the requested window; keep detailed date checks and story
  eligibility explanations in `sources.md`. Mention dates or older background in
  narration only when they help the listener understand the story.
- Do not invent facts, quotes, sources, or scientific conclusions. Distinguish
  confirmed facts from allegations, forecasts, and preliminary research.
- If there is insufficient substantive news in the window, explain the limitation
  rather than silently widening the timeframe or padding the episode.
- Write in casual, friendly, accessible Mandarin, like a knowledgeable friend
  catching the listener up on interesting news. Use a short, welcoming introduction,
  natural transitions, useful context, and a brief sign-off. Avoid a formal bulletin
  or lecture tone. Apply the same style to the English translation.
- Lead with what happened and why it matters. Spend the listening time on the
  stories rather than explanations of the research process or repeated lessons
  about how to interpret news. Explain specialist terms briefly when useful.
- Keep caveats concise and include them only when they materially change the
  meaning: for example, an unconfirmed allegation or a mouse study rather than a
  human trial. Preserve accuracy with natural attribution, not repeated disclaimers.
  Do not explain obvious distinctions or preempt misunderstandings the wording
  already avoids. After saying "September's food price index," do not add that it
  is not October's data. Do not narrate why a publication qualifies for the window.
- Avoid exact timestamps, repeated publication dates, generic legal/medical/financial
  disclaimers, and defensive commentary unless genuinely necessary to the story.
  Keep methodological qualifications and detailed sourcing in `sources.md`.
- Use simplified Chinese by default. Produce a faithful English translation and
  select useful vocabulary from the actual script.
- Keep source links and research notes in a separate `sources.md` in the episode
  folder, not in the spoken transcripts. Include article titles, publishers,
  publication dates, URLs, and the research window.

## Text deliverables and audio preferences

- Read the existing project `podcast.toml` and follow its voices, speaking rates,
  pauses, input filenames, and section order. Do not replace these preferences
  with defaults from this brief or change the shared configuration unless asked.
- Respect any episode-specific `podcast.toml` overrides. Only create overrides
  when the current request calls for different audio settings.
- Create a new, uniquely named episode folder under `inputs/`; preserve existing
  episodes. Save Chinese and English transcripts and vocabulary using the
  configured filenames.
- Align the English and Chinese transcripts line by line, including headings,
  so interleaved playback pairs matching translations. Use matching paragraph
  breaks as well. Keep production notes out of spoken text.
- Write vocabulary as UTF-8 CSV with `chinese` and `english` columns; quote values
  containing commas. Choose relevant terms and explain their meanings in context.
- Estimate the Chinese-only duration using the configured speaking speed, not
  total bilingual word count. Treat 15 minutes as an approximate target and
  label the duration as an estimate; do not synthesize speech to measure it.
- For a new podcast, prepare the transcripts, vocabulary CSV, and `sources.md`,
  validate the inputs with the existing generator's dry-run mode, then stop.
  Do not run audio generation or audio previews, contact the speech service, or
  create audio files. The user will run the audio program themselves.
- Report the text folder, stories covered, research window, and estimated Chinese
  duration. Include the command the user can run to render the episode. Mention
  important research limitations briefly outside the spoken script.

## Example requests

> Generate a news podcast following podcast-brief.md and the existing podcast.toml.

> Follow podcast-brief.md, but focus on AI and neuroscience from the last week.

> Follow podcast-brief.md, but aim for 10 minutes of Chinese narration and cover
> China and business only.

## Amendments

Add suggestions or preference changes below as bullets. They apply to future
podcasts and override conflicting defaults above; later entries take precedence
over earlier ones. No need to repeat them in each request. Keep amendments out of
the spoken script itself.
