# DIX Modules

External DIX modules maintained by Skaldos.

Each top-level directory is a directly loadable DIX module root. For example, clone this repository
below a DIX source tree as `modules/skaldos`; then `sway/` is loaded with module ID
`skaldos/sway`.

This repository currently provides source modules and development tests. It does not promise a PyPI
package or an installer.

## Source assembly

```sh
git clone git@github.com:skaldos/dix.git
cd dix/modules
git clone git@github.com:skaldos/dix-modules.git skaldos
```

The optional artifacts below each module's `integrations/` directory stay owned by that module and
are ignored by DIX module-definition inspection.
