# Third-party notices

Release Atlas implementation and original synthetic data are MIT licensed.

The standalone HTML bundles React, React DOM and Scheduler. Their notices are preserved below and legal comments are retained in the generated bundle. Source development dependencies and Python packages are restored from the exact lockfiles; they are not vendored in this repository. Installed dependency distributions retain their own licenses. A server image includes those distributions and their license files. Review dependency licenses before redistribution in a different form.

## Bundled documentation examples

`data/demo-documents/` contains original fictional MIT-licensed documentation written for Release Atlas with AI assistance. It is not third-party Pallets material. The Sources demo button now uses that synthetic corpus.

`data/demo-readmes/snapshots.json` retains licensed regression fixtures containing verbatim public README snapshots from Werkzeug (the myurch/werkzeug fork), Flask, Jinja, Click, MarkupSafe and Quart. These documents are third-party material, separate from the original synthetic demonstration data. Each snapshot records its repository, immutable commit, original README URL, content fingerprint and license URL. The bundle's [provenance record](data/demo-readmes/README.md) lists the commits. The corresponding complete copyright and license notices are retained in [data/demo-readmes/licenses](data/demo-readmes/licenses): Werkzeug, Flask, Jinja, Click and MarkupSafe use BSD-3-Clause; Quart uses MIT. Preserve these notices when redistributing this bundle. No endorsement by these projects is implied.

## react

MIT License

Copyright (c) Meta Platforms, Inc. and affiliates.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## react-dom

MIT License

Copyright (c) Meta Platforms, Inc. and affiliates.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## scheduler

MIT License

Copyright (c) Meta Platforms, Inc. and affiliates.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


## Optional local semantic encoder

Ask Atlas can use the Sentence Transformers [all-MiniLM-L6-v2 model](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, under Apache License 2.0. The model is a third-party pretrained artifact, not original Release Atlas training data. It is downloaded only by the optional setup script, verified against pinned hashes and stored outside Git and the standalone HTML. The setup preserves the [Apache-2.0 license](https://www.apache.org/licenses/LICENSE-2.0.txt) next to the weights. ONNX Runtime, Tokenizers and their dependencies retain their installed distribution licenses. These optional dependencies are pinned in `requirements-semantic.txt` and are not vendored.
