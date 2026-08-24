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
is based on `ularch/Easy_Cidaren` and preserves its attribution.
Asterism-specific orchestration and UI are maintained separately.
