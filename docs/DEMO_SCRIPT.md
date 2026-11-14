# Revenant: demo script (target 2:45, hard limit 3:00)

Rules: public YouTube, no copyrighted music (silence or self-made/royalty-free licensed track), every simulated element labelled on screen ("SIMULATED HANDSET" / "AT SANDBOX SIMULATOR" / "REAL HANDSET"). No claims beyond what is shown. Pre-record fallback takes of every step; the live compile uses a warm cache AND a fresh Kiro run recorded in the same take if the key works (U1).

Set-up before recording: handset (real feature phone with SIM) on table, charged, in frame; SMS provider path verified (U5); console open at `/crypt`; AT simulator tab ready with the clinic channel; emulator tab ready; farmer MCP running; `.kiro/` visible in a terminal split.

| Time | Visual | Narration (short) | Proof shown |
|---|---|---|---|
| 0:00-0:12 | Close-up of real feature phone, dark screen, signal bars flicker on. Title "REVENANT". | "Feature phones still carry the continent. Your API cannot reach them. Revenant compiles it to USSD." | device in frame |
| 0:12-0:40 | Console: upload `clinic.openapi.yaml`. Stages Exhume, Reanimate run. Terminal split shows `kiro-cli chat --no-interactive --agent ussd-annotator` stream. "Buried: 2 operations" tombstones appear (nested address object, date-time). | "OpenAPI in. Unsupported shapes are buried with a reason, not guessed. A Kiro headless agent proposes labels and menu layout. Its output is schema-checked." | Kiro run id, annotator badge, refusal codes |
| 0:40-1:00 | State graph; click PIN screen; char counter shows worst case e.g. n/182. Last Rites panel: reachability, exits, back, steps, length, PIN, SMS all green. | "Every screen fits 182 characters at worst case. Every state can exit. Back works. PIN is last and never echoed." | validator report |
| 1:00-1:35 | AT sandbox simulator (labelled): dial the clinic code, 1 Book, pick clinic, day, slot, enter PIN (digits not shown), `END Booked ... SMS sent`. Cut to real handset: SMS arrives, hold to camera. | "Dialled from the Africa's Talking sandbox. The confirmation lands by SMS on a real handset." | live callback, real SMS |
| 1:35-2:25 | Console: paste farmer-prices MCP URL. Compile live (cached annotations as fallback). Graph appears; one tool refused (free-text note). Emulator (labelled): crop, market, price screen; "price history" returns long result: `END Sent by SMS`; inbox shows full history; handset buzzes with same text. | "Second app, new input type: an MCP server. Long answers fall back to SMS. No model is involved while the user dials." | MCP ingestion, SMS fallback |
| 2:25-2:40 | Split: `generated/clinic-booking` and `generated/farmer-prices` folders; `pytest -m pbt` output with Hypothesis seed and counts; `.kiro/` tree. | "One compiler, two independently deployable apps. Property tests check the compiler itself. Built with Kiro specs, steering, hooks, a custom agent and MCP." | folders, test output, `.kiro` |
| 2:40-2:45 | Tombstone logo, "GSM rising from the grave", repo URL and live URL. | "Revenant. Developer infrastructure for the next billion screens that are not screens." | URLs |

Fallback rules:
- Kiro fails live: switch to the pre-recorded run, say "cached run", UI already shows `annotator: cached`.
- AT simulator down: use emulator only, state it; handset SMS still via modem.
- Real handset SMS not arriving: show pre-recorded take; never fake.

Submission companions: written explanation of Kiro usage (specs, steering, hooks, custom agent, MCP, PBT, headless step with evidence path); "how to test" page `/judges` with emulator link and demo credentials; hardware note offering physical access.
