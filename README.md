# hermes-evol

**Subconscious observer plugin for Hermes Agent.**

Background awareness engine. Continuously probes, absorbs, reflects, explores, expresses, and memorizes.

## Install

```bash
./install.sh conductor
```

## Enable

In profile `config.yaml`:
```yaml
plugins:
  enabled:
    - hermes-evol
```

Restart gateway: `hermes --profile conductor gateway restart`

## Tools

`evol_status`, `evol_material`, `evol_config`, `evol_speak`, `evol_reflect`, `evol_explore`, `evol_cycle`

## Dev

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```
