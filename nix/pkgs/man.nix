# Man pages from docs/**/*.md, one per `title:`, built by libexec/ws-doc-build
# (lowdown -s -t man) with lowdown from nixpkgs.
{ runCommand, lowdown }:
runCommand "workstation-man" { nativeBuildInputs = [ lowdown ]; } ''
  mkdir -p work/man/man1
  cp -r ${../../docs} work/docs
  WS_DOC_ROOT="$PWD/work" sh ${../../libexec/ws-doc-build} > /dev/null
  mkdir -p $out/share/man
  cp -r work/man/man1 $out/share/man/man1
''
