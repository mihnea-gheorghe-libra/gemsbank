# `payments/application`

Use cases and the ports **payments** needs from other modules, expressed as interfaces. This is what
other modules are allowed to import — never `payments/domain` or `payments/adapters` directly.

Commands handled here are reached only through `platform/commandbus`, never called directly by
an HTTP handler.
