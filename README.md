# Easy_Cidaren_Backend

Headless Cidaren backend used by Asterism. It retains the proven API, task,
question, answer and submission logic from
[`ularch/Easy_Cidaren`](https://github.com/ularch/Easy_Cidaren), while removing
the desktop UI, bundled token-capture executables and MITM workflow.

This repository also contains the current WeChat OAuth V2 login used by
Asterism: the service displays an authorization URL or QR code, the user opens
it in WeChat, and the final callback URL is exchanged for an account-bound
token and `jv=99` crypto context.

## Integration boundary

This is a backend library, not a standalone user interface. Asterism owns the
WebUI, accounts, encrypted credential storage, scheduling, jobs, logs, question
bank and reviewed answers. Its Cidaren Worker imports this repository and calls
the backend modules directly.

Important modules:

- `api/oauth.py`: WeChat authorization and callback exchange.
- `api/login.py`: token/session validation.
- `api/basic_api.py`: course and vocabulary inventory.
- `api/main_api.py`: class tasks and assessment operations.
- `answer_questions/`: donor answer selection and submission behavior.
- `decryptencrypt/debase64.py`: legacy JV decoding and OAuth-bound `jv=99`.

## License and provenance

Licensed under GPL-3.0, following the upstream project. The backend extraction
is based on `ularch/Easy_Cidaren` revision
`2ce37edca67f00954d610f2d770cb6bb4082d5fd` and preserves its attribution.
Asterism-specific orchestration and UI are maintained separately.

## 2026-11-07 integration status

The desktop fork now reuses this repository's OAuth V2 login and headless runner:
[MOPELotus/Easy_Cidaren](https://github.com/MOPELotus/Easy_Cidaren).
This library keeps its headless boundary and does not depend on Qt or MITM.

The OAuth request version follows the official H5 build `2.7.0.261019_01`.
Full response envelopes now honor their embedded `jv=99`, and malformed callback
ports fail as OAuth errors. Synthetic handshake and authenticated-decryption tests
cover these paths. Real WeChat authorization still requires the account owner.

## Lotus-first answer provider (2026-11-07)

All questions first use Lotus OCS `POST /search`. Configure
`EASY_CIDAREN_LOTUS_TOKEN` and optionally `EASY_CIDAREN_LOTUS_URL`
(default `https://tiku.lotusshared.cn/search`), or an untracked
`config/lotus.json` containing `url`, `token` and optional `timeout` seconds.
This public repository contains no production credential.

On missing, manual-only, malformed or unavailable Lotus answers, the original
answer bank, vocabulary/rule matching and guessing logic is used. Unsupported
questions in both paths are skipped. `set_answer_override()` supplies an optional
fallback only; it never bypasses a successful Lotus answer.

Images preserve stem/option ownership, including native Cidaren base64 flags
`enable_i_i` and `enable_i_o`. Official `stem.ph_en_url` / `ph_us_url` and TTS
paths are sent as `audio` for the Lotus server's Whisper ASR. Explicit audio
lists, native image mappings and string `context` are also forwarded.
Mode 13 is sentence-to-sentence choice; listening modes are 21/22.
Variant mode IDs normalize to their first two digits, matching the official UI.

Results include `lotus_answer_count` and `fallback_answer_count`. Counts measure
successfully submitted questions, once per task/topic; retries and multiple
submissions for a matching question do not double-count, and skips are excluded.

Run `python -m unittest discover -s tests`. Set `OCS_AI_SOURCE` to the installed
OCS adapter to additionally test its real server, image handling, context, audio
transcript insertion, parser and normalizer with synthetic model/ASR runners.
A production Cidaren public MP3 has separately passed real Whisper and Lotus
answering. Real account course submissions remain unverified.
