### Beveren Health

Beveren Health

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app beveren_health
```

#### Dependencies

This app requires the `python-barcode` library for barcode image generation:

```bash
bench pip install python-barcode[images]
```

Or add it to your `requirements.txt`:
```
python-barcode[images]
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/beveren_health
pre-commit install
```

A commit that reformats whole files (for example the first `pre-commit run
--all-files`) makes Semgrep report the pre-existing findings of those files as
new, because its baseline matches changed lines. Such a one-off commit can skip
the Semgrep hook locally and in CI:

```bash
SKIP=semgrep git commit -m "chore: apply pre-commit formatting [skip semgrep]"
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade
- [Frappe Semgrep rules](https://github.com/frappe/semgrep-rules) (only findings
  introduced by the change are reported, see `scripts/run_semgrep.sh`)
### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on the `develop` branch and pull
  requests. The `linters` job runs the Frappe Semgrep rules (new findings only)
  on every push and pull request.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
