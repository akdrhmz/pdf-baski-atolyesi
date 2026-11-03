"""Pencere kabuğunun yapısı (Tk'siz, yalnızca kaynak koduna bakar).

2.8'de ``app.py`` ince kabuğa indi; kurulum, belge yükleme, işlem hattı özeti ve
kısayollar karışımlara taşındı. Bu testler o düzenin bozulmamasını korur.
"""

import ast
import builtins
import os
import symtable

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ModernGutterApp'ın MRO sırası (app.py'deki taban sırasıyla aynı olmalı)
SHELL_CLASSES = [
    ("app.py", "ModernGutterApp"),
    ("ui/config_binding.py", "ConfigBindingMixin"),
    ("ui/shell_build.py", "ShellBuildMixin"),
    ("ui/pipeline.py", "PipelineMixin"),
    ("ui/document.py", "DocumentMixin"),
    ("ui/shortcuts.py", "ShortcutsMixin"),
    ("ui/merge_job.py", "MergeJobMixin"),
    ("ui/dialogs.py", "DialogsMixin"),
    ("ui/workflow.py", "WorkflowMixin"),
    ("ui/dnd.py", "DropMixin"),
]


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as handle:
        return handle.read()


def _class_node(rel, name):
    tree = ast.parse(_read(rel))
    return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)


def test_app_py_stays_a_slim_shell():
    lines = _read("app.py").count("\n") + 1
    assert lines <= 460, f"app.py {lines} satır; yeni kod kabuğa değil ilgili karışıma/sekmeye girmeli"


def test_app_class_bases_match_the_declared_order():
    bases = [b.id for b in _class_node("app.py", "ModernGutterApp").bases]
    assert bases == [name for _, name in SHELL_CLASSES[1:]] + ["StudioWindow"]


def test_no_method_is_defined_in_two_shell_classes():
    """Bir ad iki karışımda tanımlıysa MRO sırası sessizce kazananı seçer; bunu yasakla."""
    seen = {}
    for rel, name in SHELL_CLASSES:
        node = _class_node(rel, name)
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                # property ve setter aynı sınıfta aynı adı paylaşır; bu bir çakışma değildir
                key = item.name
                owner = seen.setdefault(key, (rel, name))
                assert owner == (rel, name), f"{key}: {owner} ve {(rel, name)} içinde tanımlı"


def test_assets_dir_points_at_the_real_assets():
    from ui.paths import ASSETS_DIR

    assert os.path.isfile(os.path.join(ASSETS_DIR, "icon.png"))
    assert os.path.isfile(os.path.join(ASSETS_DIR, "icon.ico"))
    assert os.path.isfile(os.path.join(ASSETS_DIR, "DejaVuSans.ttf"))


def test_forward_descriptor_reads_and_writes_through_the_target():
    from ui.bridge import forward

    class Inner:
        value = 1

    class Outer:
        alias = forward("inner", "value")

        def __init__(self):
            self.inner = Inner()

    outer = Outer()
    assert outer.alias == 1
    outer.alias = 7
    assert outer.inner.value == 7
    assert isinstance(Outer.alias, forward)  # sınıf üzerinden erişim tanımlayıcıyı verir


def test_no_ui_module_builds_an_assets_path_from_its_own_file():
    """``ui/`` içindeki bir dosyanın ``__file__``'ı proje kökü değildir (Hakkında simgesi bu yüzden kayboldu)."""
    offenders = []
    for rel in _project_modules():
        if rel == "app.py" or rel == "ui/paths.py":
            continue
        if '"assets"' in _read(rel):
            offenders.append(rel)
    assert not offenders, offenders


# --- Tanımsız ad kontrolü -------------------------------------------------------

def _module_names(tree, seen=()):
    names = set()

    def visit(body):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(n.name)
            elif isinstance(n, ast.Import):
                names.update((a.asname or a.name).split(".")[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    if a.name != "*":
                        names.add(a.asname or a.name)
                        continue
                    path = os.path.join(ROOT, n.module.replace(".", os.sep) + ".py")
                    if os.path.exists(path) and path not in seen:
                        sub = ast.parse(open(path, encoding="utf-8").read())
                        names.update(x for x in _module_names(sub, seen + (path,)) if not x.startswith("_"))
            elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for target in targets:
                    names.update(x.id for t in [target] for x in ast.walk(t) if isinstance(x, ast.Name))
            elif isinstance(n, (ast.For, ast.With, ast.If, ast.While, ast.Try)):
                for field in ("body", "orelse", "finalbody"):
                    visit(getattr(n, field, []) or [])
                for handler in getattr(n, "handlers", []):
                    visit(handler.body)

    visit(tree.body)
    return names


def undefined_globals(rel):
    """``rel`` içindeki, modülde ve yerleşiklerde bulunmayan global başvuruları döndürür."""
    source = _read(rel)
    known = _module_names(ast.parse(source)) | set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
    bad = set()

    def walk(table):
        for symbol in table.get_symbols():
            if symbol.is_referenced() and symbol.is_global() and not symbol.is_assigned():
                if symbol.get_name() not in known:
                    bad.add((table.get_name(), symbol.get_name()))
        for child in table.get_children():
            walk(child)

    walk(symtable.symtable(source, rel, "exec"))
    return sorted(bad)


def _project_modules():
    for rel in ("app.py",):
        yield rel
    for folder in ("ui", os.path.join("ui", "tabs")):
        for name in sorted(os.listdir(os.path.join(ROOT, folder))):
            if name.endswith(".py"):
                yield os.path.join(folder, name).replace(os.sep, "/")


def test_no_module_references_an_undefined_global():
    problems = {rel: undefined_globals(rel) for rel in _project_modules()}
    problems = {rel: bad for rel, bad in problems.items() if bad}
    assert not problems, problems
