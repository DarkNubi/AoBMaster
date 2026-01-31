# CI Integration Examples for AoBMaster

This directory contains example CI/CD workflows for integrating AoBMaster into automated pipelines.

## GitHub Actions

### Basic Signature Generation

Create `.github/workflows/aob-gen.yml`:

```yaml
name: Generate AoB Signatures

on:
  push:
    paths:
      - 'binaries/**'
  workflow_dispatch:

jobs:
  generate-signatures:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install AoBMaster
        run: pip install -e .
      
      - name: Generate signatures for all binaries
        run: |
          mkdir -p output
          for binary in binaries/*.exe; do
            echo "Processing $binary..."
            aobmaster synth \
              --base "$binary" \
              --anchor-rva 0x1000 \
              --format json \
              > "output/$(basename $binary .exe)_signatures.json"
          done
      
      - name: Upload signatures
        uses: actions/upload-artifact@v4
        with:
          name: aob-signatures
          path: output/
```

### Multi-Version Validation

```yaml
name: Validate Signatures Across Versions

on:
  push:
    branches: [ main ]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install AoBMaster
        run: pip install -e .
      
      - name: Validate signatures
        run: |
          aobmaster synth \
            --base binaries/game_v1.0.exe \
            --anchor-rva 0x1234 \
            --versions binaries/game_v1.1.exe binaries/game_v1.2.exe \
            --format json \
            --profile balanced \
            --context-variations on \
            > signatures.json
          
          # Check if we got valid candidates
          python -c "
          import json
          with open('signatures.json') as f:
              data = json.load(f)
          valid = [c for c in data['candidates'] if c['valid']]
          if not valid:
              print('ERROR: No valid signatures found!')
              exit(1)
          print(f'SUCCESS: Found {len(valid)} valid signatures')
          "
```

## Best Practices

1. **Always validate** signatures across multiple versions in CI
2. **Use --profile balanced** for most scenarios
3. **Enable --context-variations on** for better coverage
4. **Set --top-n** appropriately (5-10 for most cases)
5. **Archive signatures** as artifacts for debugging
6. **Monitor confidence scores** - fail if confidence < 0.5
7. **Use deterministic** settings for reproducible builds
