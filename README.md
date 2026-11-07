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

## Lotus-only answer provider (2026-11-07)

All automatic answers now come exclusively from the Lotus OCS `POST /search`
endpoint. Configure `EASY_CIDAREN_LOTUS_TOKEN` and optionally
`EASY_CIDAREN_LOTUS_URL` (default `https://tiku.lotusshared.cn/search`), or create
an untracked `config/lotus.json` with `url`, `token` and optional `timeout` (seconds).
No production credentials are included in this public library.

Manual-only, missing, malformed or unsupported answers are skipped; transport,
authentication and service failures stop the task. There is no local answer bank,
rule-based or random fallback. Local self-learning writes are disabled.
`set_answer_override()` is rejected to prevent bypassing the sole provider.
The runner checks credentials before starting task operations.

Choice letters are mapped to original Cidaren answer tags, preserving option
order, nested options and string tags. Supported mappings include choices,
matching, phrase and spelling blanks. Audio-only mode 13 is skipped until an
explicit audio protocol is implemented. Never guess an unheard audio answer.

Run `python -m unittest discover -s tests`. Set `OCS_AI_SOURCE` to the installed
OCS adapter to additionally test the real server, parser and normalizer with a
synthetic model. Real course submissions still require an authorized account.
