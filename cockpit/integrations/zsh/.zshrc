# DIX Cockpit owns this complete Zsh workspace. Do not source host startup files here.
umask 077

HISTFILE=${HISTFILE:?Cockpit HISTFILE is required}
HISTSIZE=20000
SAVEHIST=20000
setopt append_history share_history hist_ignore_dups

autoload -Uz compinit
compinit -d "$ZDOTDIR/.zcompdump"

_dix_cockpit() {
  _arguments '1:command:(start attach status stop reset)' '*:argument:'
}
_dix_roba_cli() {
  _arguments '*:argument:'
}
_roba_ctl() {
  _arguments '*:argument:'
}
compdef _dix_cockpit dix-cockpit
compdef _dix_roba_cli dix-roba-cli
compdef _roba_ctl roba-ctl

PROMPT='%F{39}[cockpit:%m:%1~]%f %# '
