# CI/CD Integration Examples for AoBMaster

This directory contains example CI/CD pipeline configurations for testing AoB signatures in continuous integration environments.

## Available Integrations

### Azure DevOps (`azure-pipelines.yml`)

**Features:**
- Tests signatures against binary corpus
- Performs temporal stability analysis
- Publishes test results and artifacts
- Fails build on critical alerts

**Usage:**
1. Copy `azure-pipelines.yml` to your repository root
2. Configure binary corpus location
3. Add to Azure Pipelines

### Jenkins (`Jenkinsfile`)

**Features:**
- Parameterized pipeline for flexibility
- Tests signatures with configurable parallelism
- Stability analysis with alert checking
- Archives results as build artifacts

**Usage:**
1. Copy `Jenkinsfile` to your repository
2. Configure in Jenkins as Pipeline project
3. Set parameters as needed

### CircleCI (`.circleci/config.yml`)

**Features:**
- Docker-based execution
- Parallel workflow support
- Artifact storage
- Test result tracking

**Usage:**
1. Copy `.circleci/` directory to your repository root
2. Configure CircleCI project
3. Adjust parameters in config

## Common Configuration

All pipelines follow a similar structure:

1. **Setup**: Install AoBMaster and dependencies
2. **Test**: Run signature tests against binary corpus
3. **Validate**: Check test results and fail on errors
4. **Analyze**: Perform temporal stability analysis
5. **Alert**: Check for critical stability issues
6. **Archive**: Store results as artifacts

## Customization

### Binary Corpus

Point to your binary corpus using glob patterns:

```yaml
--corpus "binaries/**/*.exe"    # All .exe files recursively
--corpus "test-bins/*.dll"       # Only .dll files
--corpus "corpus-v{1,2}/*.exe"   # Multiple versions
```

### Parallel Workers

Adjust parallelism based on available resources:

```yaml
--parallel 4    # 4 workers (default)
--parallel 8    # 8 workers (for larger corpus)
--parallel 1    # Sequential (for debugging)
```

### Recording Results

Enable database recording to build historical data:

```yaml
--record         # Record test results to database
```

This enables temporal analysis and trend detection.

## Example Workflow

```bash
# 1. Test all signatures
aobmaster test --db signatures.db \
  --corpus "binaries/*.exe" \
  --parallel 4 \
  --record \
  --format json > results.json

# 2. Check results
cat results.json | jq '.summary'

# 3. Analyze stability
aobmaster analyze --db signatures.db \
  --format json > analysis.json

# 4. Check for alerts
cat analysis.json | jq '.analyses[].alerts[] | select(.severity=="critical")'
```

## Exit Codes

All pipelines use standard exit codes:

- **0**: All tests passed, no critical alerts
- **1**: Test failures or critical alerts detected
- **2**: Configuration or runtime error

## Best Practices

1. **Corpus Management**: Keep binary corpus up to date with target versions
2. **Database Storage**: Store signature database as CI artifact
3. **Historical Data**: Enable `--record` to track trends over time
4. **Alert Thresholds**: Adjust critical alert handling based on your needs
5. **Parallel Testing**: Scale workers based on corpus size and CI resources

## Troubleshooting

### Tests Failing in CI

- Verify binary corpus is accessible in CI environment
- Check database file is present and readable
- Ensure Python version is 3.8+

### Performance Issues

- Increase `--parallel` workers (max: CPU cores)
- Consider splitting large corpus into smaller batches
- Use faster CI agents if available

### False Positives

- Review signature specificity (wildcard ratio)
- Check for version-specific signatures
- Consider using multi-version synthesis

## Integration with Existing Workflows

These examples can be integrated with:

- Pull Request validation
- Nightly builds
- Release verification
- Deployment gates

Example: PR validation
```yaml
on:
  pull_request:
    paths:
      - 'signatures/**'
      - 'binaries/**'
```

## Support

For more information:
- Documentation: `aobmaster --help`
- SDK Reference: See `V2.1_IMPLEMENTATION_PLAN.md`
- Issues: Open an issue on GitHub

## Version Compatibility

These examples require:
- AoBMaster v2.1.0+
- Python 3.8+
- Access to binary corpus

## License

These configuration examples are provided as-is under the same license as AoBMaster.
