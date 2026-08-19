# `/register` — onboarding wizard

Renders archive screen 01 as a four-step wizard. Entry point: `apps/web/index.html`, served by the
API at `http://localhost:8000/app/`.

| Step | Component | Call |
|---|---|---|
| 01 ID document | `components/onboarding/DocumentStep.jsx` | `POST /onboarding/{id}/document` |
| 02 Contact | `components/onboarding/ContactStep.jsx` | `POST /onboarding/{id}/contact` |
| 03 Email signature | `components/onboarding/CodeStep.jsx` | `POST /onboarding/{id}/code/verify`, `.../code/resend` |
| 04 Credentials | `components/onboarding/CredentialsStep.jsx` | `POST /onboarding/{id}/complete` |

`RegisterPage.jsx` owns all state and every network call. The step components are presentational:
they receive values and callbacks, never talk to `GEMS.api` themselves.

## Divergences from the archive

- **The selfie step is gone.** No biometric capture anywhere in the product.
- **Four steps, not five.** The rail and the `STEP n OF 4` kicker follow.
- **The code arrives by email, not SMS.** The backend's only OTP adapter is Resend. The phone
  number is still collected — it is what a future SMS or push adapter will use.
- Copy defaults to English so the screen matches the archive. `?lang=ro` switches to Romanian;
  both dictionaries live in `src/messages/`.

## No build step

React and Babel load from unpkg; `.jsx` files are transformed in the browser. This is a deliberate
consequence of having no npm on the target machine — see `apps/web/README.md`.
