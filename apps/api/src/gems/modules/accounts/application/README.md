# `accounts/application`

Use cases and the ports **accounts** needs from other modules, expressed as interfaces. This is what
other modules are allowed to import — never `accounts/domain` or `accounts/adapters` directly.

Commands handled here are reached only through `platform/commandbus`, never called directly by
an HTTP handler.
