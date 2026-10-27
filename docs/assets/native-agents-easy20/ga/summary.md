# Native GA station pilot

Model alias: gpt-5.6-luna. One sampled world, 39 fresh sessions. No statistical effect estimate.

|Task|Condition|Success|Distance|Moves|Ops|Queries|Unsupported|Relevant prior exposure|LLM calls|Continuations|Memory changes|
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|
|T1|prefix|True|21|15|19|2|0|False|27|0|global_mem.txt, global_mem_insight.txt, survey_game_sop.md|
|T2|retain|True|21|15|20|3|0|False|25|0|survey_game_sop.md|
|T2|clear|True|21|15|20|3|0|False|27|0|global_mem.txt, global_mem_insight.txt, survey_game_sop.md|
|T3|retain|True|22|16|20|0|2|True|29|0|survey_game_sop.md|
|T3|clear|True|22|16|20|1|1|True|29|0|global_mem.txt, global_mem_insight.txt, land_survey_game_sop.md|
|T4|retain|True|12|10|13|1|0|False|19|0|survey_game_sop.md|
|T4|clear|True|12|10|12|0|0|False|21|0|global_mem.txt, global_mem_insight.txt, lanting_survey_game.md|
|T5|retain|True|21|15|20|3|0|True|25|0|survey_game_sop.md|
|T5|clear|True|21|15|19|0|2|True|28|0|global_mem.txt, global_mem_insight.txt, survey_game_t5_lanting.md|
|T6|retain|True|12|10|13|1|0|False|18|0|survey_game_sop.md|
|T6|clear|True|12|10|12|0|0|False|18|0|global_mem.txt, global_mem_insight.txt, lanting_survey_game_sop.md|
|T7|retain|True|21|15|19|0|2|False|27|0|survey_game_sop.md|
|T7|clear|True|16|12|16|2|0|False|25|0|global_mem.txt, global_mem_insight.txt, survey_game_experience.md|
|T8|retain|True|12|10|12|0|0|True|17|0|survey_game_sop.md|
|T8|clear|True|12|10|12|0|0|True|19|0|global_mem.txt, global_mem_insight.txt, survey_game_sop.md|
|T9|retain|True|12|10|12|0|0|True|16|0|survey_game_sop.md|
|T9|clear|True|12|10|12|0|0|True|18|0|global_mem.txt, global_mem_insight.txt, survey_game_sop.md|
|T10|retain|True|12|10|13|1|0|True|18|0|survey_game_sop.md|
|T10|clear|True|12|10|12|0|0|True|19|0|global_mem.txt, global_mem_insight.txt, survey_game_sop.md|
|T11|retain|True|12|10|13|1|0|True|20|0|survey_game_sop.md|
|T11|clear|True|12|10|13|1|0|True|19|0|global_mem.txt, global_mem_insight.txt, survey_game_sop.md|
|T12|retain|True|16|12|16|2|0|True|21|0|survey_game_sop.md|
|T12|clear|True|21|15|19|0|2|True|28|0|global_mem.txt, global_mem_insight.txt, survey_game_sop.md|
|T13|retain|True|21|15|19|0|2|True|24|0|survey_game_sop.md|
|T13|clear|True|21|15|19|0|2|True|26|0|global_mem.txt, global_mem_insight.txt, lanting_survey_game_sop.md|
|T14|retain|True|16|12|16|2|0|False|21|0|survey_game_sop.md|
|T14|clear|True|16|12|16|2|0|False|23|0|global_mem.txt, global_mem_insight.txt, survey_game_sop.md|
|T15|retain|True|12|10|12|0|0|True|16|0|survey_game_sop.md|
|T15|clear|True|12|10|13|1|0|True|20|0|global_mem.txt, global_mem_insight.txt, survey_game_sop.md|
|T16|retain|True|15|11|13|0|0|True|19|0|survey_game_sop.md|
|T16|clear|True|12|10|12|0|0|True|19|0|global_mem.txt, global_mem_insight.txt, survey_game_experience.md|
|T17|retain|True|12|10|12|0|0|True|18|0|survey_game_sop.md|
|T17|clear|True|12|10|13|1|0|True|18|0|global_mem.txt, global_mem_insight.txt, lanting_survey_experience.md|
|T18|retain|True|20|12|14|0|0|True|26|0|survey_game_sop.md|
|T18|clear|True|16|12|16|2|0|True|26|0|global_mem.txt, global_mem_insight.txt, survey_game_sop.md|
|T19|retain|True|15|11|13|0|0|True|20|0|survey_game_sop.md|
|T19|clear|True|21|15|20|3|0|True|26|0|global_mem.txt, global_mem_insight.txt, survey_game_sop.md|
|T20|retain|True|12|10|12|0|0|True|18|0|survey_game_sop.md|
|T20|clear|True|12|10|12|0|0|True|19|0|global_mem.txt, global_mem_insight.txt, survey_game_experience.md|
