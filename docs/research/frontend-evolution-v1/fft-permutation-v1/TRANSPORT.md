# Lossless raw-output transport

`size.txt.b64` is base64 transport of the exact original `size.txt`, including its final blank line. The original bytes and SHA-256 recorded in `manifest.json` are unchanged. This avoids new whitespace diagnostics without weakening repository checks or editing raw evidence.

Before verification or reproduction, decode from this directory:

```sh
base64 --decode size.txt.b64 > size.txt
```

All other manifest members are stored directly. No experiment was rerun for this transport-only change.
