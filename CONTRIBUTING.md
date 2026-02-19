# Contributing

## Development

### Syncing from the active Talon installation

If you develop recall as part of a larger Talon config and maintain this standalone package separately, use the sync script:

```bash
cd /path/to/standalone-recall
.scripts/sync_from_active.sh
```

This copies the core files from your active installation and checks that all action dependencies are satisfied by the standalone shims in `recall_core.py`.
