# Native application build artifacts

`python3 scripts/distribution/assemble_native_image.py` combines the prepared
third-party bundle with the Inkflip wheel. The Docker build consumes these
files from `native/dist/`:

| File | Purpose |
| --- | --- |
| `app.wheel.json` | Application filename, SHA-256, byte count and lock entry |
| `wheels/inkflip-*-py3-none-any.whl` | Built application wheel |
| `requirements.lock` | Complete hashed dependency and application lock |
| `notices/INDEX.json` | License notice inventory |
| `tesseract/tesseract.stamp.json` | Hashed OCR runtime inputs |
| `tesseract/debs/*.deb` | Offline-installable OCR executable and libraries |
| `BUILD-CONTEXT.json` | Platform, ABI, wheel and runtime identities |

`config/distribution-manifest.json` declares the `application_wheel` fields.
`scripts/check_native_image_inputs.py` validates the hashed application pin
and wheel tag. The wheel bytes and their digest must come from the same
build; a package-name match in a lock file is insufficient.

The committed `release/native-requirements.lock` describes third-party
inputs. The assembler writes the complete application lock under
`native/dist/` without modifying that input lock.
