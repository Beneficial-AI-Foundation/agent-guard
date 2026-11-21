import Guard

/-! Glob matcher examples. `#guard` fails the build if an expression is false. -/

open Guard.Impl

#guard glob "github.get_*" "github.get_file_contents"
#guard !glob "github.get_*" "github.issue_read"
#guard glob "main" "main"
#guard !glob "main" "Main"
#guard !glob "main" "main2"
#guard glob "*/demo-private" "octo-demo/demo-private"
#guard !glob "*/demo-private" "a/b/demo-private"        -- `*` stops at `/`
#guard glob "**/demo-private" "a/b/demo-private"        -- `**` doesn't
#guard glob ".github/workflows/**" ".github/workflows/ci.yml"
#guard glob ".github/workflows/**" ".github/workflows/sub/ci.yml"
#guard !glob ".github/workflows/*" ".github/workflows/sub/ci.yml"
#guard glob "**.github/**" "./.github/workflows/x.yml"
#guard glob "**.github/**" ".github/CODEOWNERS"
#guard !glob "**.github/**" "github/x"
#guard glob "fix/?" "fix/a"
#guard !glob "fix/?" "fix/ab"
#guard !glob "fix/?" "fix//"
#guard glob "*" ""
#guard glob "**" "a/b/c"
#guard !glob "" "a"
#guard glob "" ""
#guard glob "a***b" "a/x/yb"                              -- `***` = `**` then `*`
#guard glob "*a*a*a*a*b" "aaaaaaaaaab"
#guard !glob "*a*a*a*a*b" "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
