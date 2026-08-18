# `identity/application`

Use cases and the ports **identity** needs from other modules, expressed as interfaces. This is what
other modules are allowed to import — never `identity/domain` or `identity/adapters` directly.

Commands handled here are reached only through `platform/commandbus`, never called directly by
an HTTP handler.
