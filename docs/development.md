# Development Security

The repository uses SSH-signed Git commits.

The GitHub account is `joaomj`. The signing key title is:

```text
Asus Vivobook GitHub SSH signing key
```

The public key fingerprint is:

```text
SHA256:Y/3JXNYwCqBs1uMEYBADeKtQyZmex8rNXXCtJrcnuUo
```

The private key stays in:

```text
~/.ssh/github_asus_vivobook_ed25519
```

Keep the private key outside this repository. Do not add it to Git.

Configure this repository to sign commits:

```bash
git config gpg.format ssh
```

Verify a local commit signature:

```bash
```

Verify the commit status on GitHub:

```bash
  --jq '.commit.verification'
```

## Run the Tests

The repository uses `uv` for its development environment. Run the full suite:

```bash
uv run python -m unittest discover -s tests
```

The tests use only the Python standard library. The `pyproject.toml` file
declares the project as a non-package so `uv run` does not build or install
the service code.
