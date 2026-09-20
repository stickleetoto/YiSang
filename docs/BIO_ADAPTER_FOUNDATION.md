# YiSang BIO Adapter Foundation

This package is an YiSang-side integration boundary. It does not modify, vendor, or fork BIO.

## Dependency direction

~~~text
YiSang MemoryProvider
        |
        +-- NativeMemoryProvider -> existing YiSang MemoryPort
        |
        +-- BioMemoryProvider
              |
              v
        BioMemoryClient
              |
              v
        BioBridgeClientAdapter
              |
              v
      caller-supplied BioMemoryBridge
~~~

BIO remains optional. Importing YiSang does not import bio_overlay.

## Write boundary

BioMemoryProvider.remember() creates a BIO memory write proposal only. It never approves or directly commits that proposal. This preserves BIO ownership of lifecycle/governance.

## Read mapping

BIO current / active memories map to active YiSang MemoryRecord views. Terminal states such as stale, superseded, and archived are mapped as inactive so they cannot silently re-enter current recall.

BIO storage authority is not treated as proof of factual truth: trust_class remains unknown unless a later evidence-aware contract says otherwise.

## Direct bridge usage

The adapter is duck typed. A caller that has BIO installed may construct its own BioMemoryBridge and pass it into BioBridgeClientAdapter.

YiSang deliberately does not declare BIO as a package dependency.
