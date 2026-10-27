# Native Hermes station pilot

Model alias: gpt-5.6-luna. One sampled world, 39 fresh sessions. No statistical effect estimate.

|Task|Condition|Success|Distance|Moves|Ops|Queries|Unsupported|Relevant prior exposure|LLM calls|Continuations|Memory changes|
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|
|T1|prefix|True|21|15|19|0|2|False|30|0|memories/MEMORY.md, memories/MEMORY.md.lock, skills/.locks/cfc71096f5447fa97804e139ee75c68f4be9502ab87cc9b31bdb6e9d24fe6469.lock, skills/.usage.json, skills/.usage.json.lock|
|T2|retain|True|21|15|20|3|0|False|29|0|memories/MEMORY.md, skills/.locks/41702247d7ad9fa137e072a604797c58a1b5e3038021a6f725dd9e345e4433af.lock|
|T2|clear|True|21|15|19|0|2|False|31|0|memories/surveying-game.md, skills/.locks/6364806fd0d50f3175ae1bd64328bb9cc10481f66cd45c63f1526d7fea441572.lock|
|T3|retain|True|22|16|20|0|2|True|33|0|memories/MEMORY.md, skills/.locks/380d0ae457d65c2e8b5ac464570e6f80c2e6edcecd4baac5d8ec6afc1657f7ee.lock|
|T3|clear|True|22|16|21|3|0|True|36|0|memories/game-survey.md, skills/.locks/6364806fd0d50f3175ae1bd64328bb9cc10481f66cd45c63f1526d7fea441572.lock|
|T4|retain|True|12|10|12|0|0|False|22|0|.curator_backups/blobs/1a28f4077be781e30c482e04f7a2216248e940afad9d8ac20ae8ffdefc9ca921, .curator_backups/blobs/c6fe30ea1ac5ed4fe9f82f80fcd1a24b3dcc7a8f7d39caf5090df4ac2f5f515d, memories/MEMORY.md, skills/.curator_ledger.jsonl, skills/.locks/0eddb003b023b4c5b3fa867a8f89e11b176280d0f10ac9ee3c0cdd983e48685e.lock, skills/.locks/ledger.lock, skills/.usage.json, skills/games/cartography-game/SKILL.md, skills/games/cartography-game/references/route-planning.md|
|T4|clear|True|12|10|12|0|0|False|21|0|memories/MEMORY.md, memories/MEMORY.md.lock, skills/.locks/d0388aabcca9ccc2b6b3ca1872c5a62e369b2ca76aa73bef1f96da624cdbdc93.lock|
|T5|retain|True|21|15|19|0|2|True|30|0|memories/MEMORY.md, skills/.usage.json|
|T5|clear|True|21|15|20|2|1|True|29|0|memories/MEMORY.md, memories/MEMORY.md.lock, skills/.locks/6364806fd0d50f3175ae1bd64328bb9cc10481f66cd45c63f1526d7fea441572.lock|
|T6|retain|True|12|10|12|0|0|False|22|0|.curator_backups/blobs/ab3b85fdd73833d81f4d3c97881b83a5c9866a28ebad1ef961b3f6307c2792b2, memories/MEMORY.md, skills/.curator_ledger.jsonl, skills/.usage.json, skills/games/cartography-game/SKILL.md|
|T6|clear|True|12|10|12|0|0|False|21|0|memories/MEMORY.md, memories/MEMORY.md.lock, skills/.locks/0eddb003b023b4c5b3fa867a8f89e11b176280d0f10ac9ee3c0cdd983e48685e.lock|
|T7|retain|True|16|12|15|0|1|False|25|0|memories/MEMORY.md, skills/.usage.json|
|T7|clear|True|16|12|16|2|0|False|33|0|cartography-lessons.md, skills/.usage.json, skills/.usage.json.lock|
|T8|retain|True|12|10|12|0|0|True|22|0|.curator_backups/blobs/9b67a58d3fa14a65dae0ce71b036a785e19e469a74041da29b52dba4e7cf2c00, memories/MEMORY.md, skills/.curator_ledger.jsonl, skills/.usage.json, skills/games/cartography-game/SKILL.md|
|T8|clear|True|12|10|13|1|0|True|26|0|game-survey.md, skills/.usage.json, skills/.usage.json.lock|
|T9|retain|True|12|10|12|0|0|True|21|0|.curator_backups/blobs/6e2f32e7714bca2f0a1a6759f9db8b8c482b225d76cdb38ded6603f93d8b3989, memories/MEMORY.md, skills/.curator_ledger.jsonl, skills/.usage.json, skills/games/cartography-game/SKILL.md|
|T9|clear|True|12|10|12|0|0|True|24|0|cartography-lessons.txt, skills/.locks/0eddb003b023b4c5b3fa867a8f89e11b176280d0f10ac9ee3c0cdd983e48685e.lock|
|T10|retain|True|15|11|13|0|0|True|21|0|.curator_backups/blobs/0ace449acbb905bfa5d7c228c6f4fa60fa06b2cbedc239cc21a6c47d877501f9, skills/.curator_ledger.jsonl, skills/.usage.json, skills/games/cartography-game/SKILL.md|
|T10|clear|True|12|10|13|1|0|True|23|0|memories/MEMORY.md, memories/MEMORY.md.lock, skills/.locks/0eddb003b023b4c5b3fa867a8f89e11b176280d0f10ac9ee3c0cdd983e48685e.lock|
|T11|retain|True|12|10|12|0|0|True|22|0|.curator_backups/blobs/f55e7c173fd961e6c6467fc7f1a9ccc78e5fc8bcba315600e6109db30f29b12d, memories/MEMORY.md, skills/.curator_ledger.jsonl, skills/.usage.json, skills/games/cartography-game/SKILL.md|
|T11|clear|True|12|10|12|0|0|True|22|0|.curator_backups/blobs/235057ee7e2d90d0ff2d6ee0346076009b8269083138db86711647623874b319, memories/MEMORY.md, memories/MEMORY.md.lock, skills/.curator_ledger.jsonl, skills/.locks/0eddb003b023b4c5b3fa867a8f89e11b176280d0f10ac9ee3c0cdd983e48685e.lock, skills/.locks/ledger.lock, skills/.usage.json, skills/.usage.json.lock, skills/productivity/cartography-game/SKILL.md|
|T12|retain|True|17|11|13|0|0|True|22|0|.curator_backups/blobs/b7c56d5a229267938b6dc9bf688df1b8d58654b50f6c26e5c2a7844eafef61de, memories/MEMORY.md, skills/.curator_ledger.jsonl, skills/.usage.json, skills/games/cartography-game/SKILL.md|
|T12|clear|True|16|12|15|0|1|True|27|0|memories/MEMORY.md, memories/MEMORY.md.lock|
|T13|retain|True|15|11|13|0|0|True|23|0|.curator_backups/blobs/01e6cb28229f4544642bcbfbe38a89f66e12ecea2f8e344bc233d35c12618b1e, memories/MEMORY.md, skills/.curator_ledger.jsonl, skills/.usage.json, skills/games/cartography-game/SKILL.md|
|T13|clear|True|21|15|19|0|2|True|32|0|memories/MEMORY.md, memories/MEMORY.md.lock, skills/.locks/0eddb003b023b4c5b3fa867a8f89e11b176280d0f10ac9ee3c0cdd983e48685e.lock|
|T14|retain|True|16|12|15|0|1|False|24|0|memories/MEMORY.md, skills/.usage.json|
|T14|clear|True|16|12|16|2|0|False|30|0|skills/.usage.json, skills/.usage.json.lock, survey-game.md|
|T15|retain|True|12|10|12|0|0|True|22|0|memories/MEMORY.md, skills/.usage.json|
|T15|clear|True|12|10|12|0|0|True|24|0|.curator_backups/blobs/7217e9bdc6ee7587ea9c698d94947521a333260de6520faebb4290004eb79900, cartography.txt, skills/.curator_ledger.jsonl, skills/.locks/b4c2638e39debe36f8e1ecf59610018acb657d56261887946f6a6cef7d878332.lock, skills/.locks/ledger.lock, skills/.usage.json, skills/.usage.json.lock, skills/productivity/cartography-survey-game/SKILL.md|
|T16|retain|True|15|11|13|0|0|True|21|0|.curator_backups/blobs/2c732735fb112cf9d516be01804ef67509c67d2bbfee309e0fa0260627c2ef22, skills/.curator_ledger.jsonl, skills/.usage.json, skills/games/cartography-game/references/route-planning.md|
|T16|clear|True|12|10|13|1|0|True|24|0|cartography-t16.md, skills/.locks/0eddb003b023b4c5b3fa867a8f89e11b176280d0f10ac9ee3c0cdd983e48685e.lock|
|T17|retain|True|12|10|12|0|0|True|19|0|.curator_backups/blobs/d6b387601735d0652b32031d02e363c1280ec0447b12c5765d59207f35a6af5c, skills/.curator_ledger.jsonl, skills/.usage.json, skills/games/cartography-game/SKILL.md|
|T17|clear|True|12|10|13|1|0|True|25|0|skills/.locks/0783ebb17faf96a6f6928f3b95cd0e5d12b0eb58098132f2a6d124ecb3700ee3.lock, t17-cartography-lessons.md|
|T18|retain|True|17|11|13|0|0|True|23|0|.curator_backups/blobs/563171d2a3de4df5d0b885bcc0fcbf2dc64377be5b75d9e47506ddd69b897d42, .curator_backups/blobs/6a364975e99ccc69962da81c10a88e2889dedaf16109c59f68c9ab3cf7e7d3e3, memories/MEMORY.md, skills/.curator_ledger.jsonl, skills/.usage.json, skills/games/cartography-game/SKILL.md|
|T18|clear|True|16|12|15|0|1|True|29|0|memories/MEMORY.md, memories/MEMORY.md.lock, skills/.locks/3f2a515c71507c9577eb62a95c0ca0c1a013b2a5abcdf609bbbf38333dc9f4d1.lock, skills/.usage.json, skills/.usage.json.lock|
|T19|retain|True|16|12|14|0|0|True|21|0|skills/.usage.json|
|T19|clear|True|22|16|20|1|1|True|31|0|memories/MEMORY.md, memories/MEMORY.md.lock, skills/.locks/cfc71096f5447fa97804e139ee75c68f4be9502ab87cc9b31bdb6e9d24fe6469.lock|
|T20|retain|True|12|10|12|0|0|True|20|0|.curator_backups/blobs/da95cd03d8cbd04e291bc1f658fd2892644c6481b217dd13915c634d9a59ced1, skills/.curator_ledger.jsonl, skills/.usage.json, skills/games/cartography-game/SKILL.md|
|T20|clear|True|12|10|13|1|0|True|23|0|cartography-experience.txt, skills/.locks/0eddb003b023b4c5b3fa867a8f89e11b176280d0f10ac9ee3c0cdd983e48685e.lock|
