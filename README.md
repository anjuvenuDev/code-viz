# code-viz

Local desktop dependency graph viewer for code repositories.

## Usage

Install the local CLI entry point:

```sh
python3 -m pip install -e .
```

From a repository or project directory:

```sh
code-viz init
```

During local development, without installing:

```sh
python3 -m code_viz init
```

The command scans the current working directory, builds a file dependency graph, and opens a native desktop window.
