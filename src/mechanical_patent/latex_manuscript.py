"""LaTeX 科研初稿：分章节 AI 写作、BibTeX、版本历史与 Pandoc 导出。

MCP 只保存受控原稿并调用无 TeX 引擎的 Pandoc 转换器；禁止远程直接
编译原始 LaTeX。完整 TeX/PDF 仅可经隔离容器与人工授权执行。
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4

from .core import PatentWorkflowError, save_json, utc_now
from .project_storage import ProjectStorage

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
SECTIONS = {
    "abstract": ("摘要", "abstract"),
    "introduction": ("引言与技术问题", "section"),
    "prior_art": ("相关工作与现有技术", "section"),
    "methods": ("技术方案与研究方法", "section"),
    "engineering": ("工程原理与理论验证", "section"),
    "results": ("结果与讨论", "section"),
    "limitations": ("适用边界与局限", "section"),
    "conclusion": ("结论", "section"),
}
_BAD = re.compile(
    r"\\(?:input|include|openin|openout|read|write|immediate|catcode|"
    r"includegraphics|graphicspath|InputIfFileExists|write18|usepackage|"
    r"bibliography|addbibresource|documentclass)\b", re.IGNORECASE
)
_REMOTE = re.compile(r"(?:https?://|file://|(?:^|[/\\])\.\.[/\\])", re.IGNORECASE)


def _id(value: str, field: str) -> str:
    if not isinstance(value,str) or not _ID.fullmatch(value):
        raise PatentWorkflowError(field + "只允许字母、数字、下划线与连字符。")
    return value


def _title(value: str) -> str:
    if not isinstance(value,str) or not 1 <= len(value.strip()) <= 300:
        raise PatentWorkflowError("标题长度不合规。")
    return value.strip()


def _tex_literal(text: str) -> str:
    # 标题来自用户输入；转义 TeX 特殊符号，不能作为任意命令执行。
    repl = {"\\": r"\textbackslash{}", "{":r"\{", "}":r"\}", "#":r"\#",
            "$":r"\$", "%":r"\%", "&":r"\&", "_":r"\_",
            "^":r"\^{}", "~":r"\~{}"}
    return "".join(repl.get(ch,ch) for ch in text)


def _safe_section(text: str) -> str:
    if not isinstance(text,str) or not 1 <= len(text) <= 120000:
        raise PatentWorkflowError("LaTeX 正文每节须为1至120000字符。")
    if _BAD.search(text) or _REMOTE.search(text):
        raise PatentWorkflowError("含文件访问、危险 TeX 原语或远程资源；请改为纯正文/公式。")
    return text


class ManuscriptWorkspace:
    """每个项目内多个案卷/论文，禁止访问其他 project_id 的数据。"""

    def __init__(self, project: ProjectStorage):
        self.project = project
        self.workspace = project.workspace
        with self.workspace.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS manuscript_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    manuscript_id TEXT NOT NULL, section_key TEXT NOT NULL,
                    revision INTEGER NOT NULL, sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL, source_path TEXT NOT NULL,
                    UNIQUE(case_id,manuscript_id,section_key,revision)
                );
            """)

    def _folder(self,case_id:str,manuscript_id:str) -> Path:
        self.workspace.status(_id(case_id,"案卷编号"))
        _id(manuscript_id,"论文编号")
        folder=self.project.root/"cases"/case_id/"manuscripts"/manuscript_id
        if folder.is_symlink() or not folder.resolve().is_relative_to(self.project.root):
            raise PatentWorkflowError("论文目录非法或路径越界。")
        return folder

    def create(self,case_id:str,title:str, manuscript_id:str="") -> dict:
        title=_title(title)
        manuscript_id = _id(manuscript_id,"论文编号") if manuscript_id else "PAPER-"+uuid4().hex[:12].upper()
        folder=self._folder(case_id,manuscript_id)
        if folder.exists():
            raise PatentWorkflowError("已有同名论文，禁止覆盖历史版本。")
        folder.mkdir(parents=True,mode=0o700,exist_ok=False)
        (folder/"sections").mkdir(mode=0o700)
        (folder/"versions").mkdir(mode=0o700)
        (folder/"exports").mkdir(mode=0o700)
        header=r"\documentclass[UTF8,11pt]{ctexart}"+"\n"+r"\usepackage{amsmath,amssymb,graphicx,booktabs,hyperref}"+"\n"
        # Bibliography is plain BibTeX and references use \cite{key}.
        body=header+r"\title{"+_tex_literal(title)+"}\n"+r"\author{研究案卷："+_tex_literal(case_id)+r"}"+"\n"
        body+=r"\date{\today}"+"\n"+r"\begin{document}"+"\n"+r"\maketitle"+"\n"
        for key,(caption,kind) in SECTIONS.items():
            body+=r"\input{sections/"+key+"}"+ "\n"
            content= (r"\begin{abstract}"+"\n"+r"待 AI 撰写摘要；所有实验结果需真实来源。"+"\n"+r"\end{abstract}"
                      if kind=="abstract" else r"\section{"+caption+"}\n待 AI 补充实际理论或来源。")
            (folder/"sections"/(key+".tex")).write_text(content+"\n",encoding="utf-8")
        body+=r"\bibliographystyle{plain}"+"\n"+r"\bibliography{references}"+"\n"+r"\end{document}"+"\n"
        (folder/"main.tex").write_text(body,encoding="utf-8")
        (folder/"references.bib").write_text("% 仅录入已核验的真实公开 DOI/公开号和文献条目\n",encoding="utf-8")
        save_json(folder/"manuscript.json",{"case_id":case_id,"manuscript_id":manuscript_id,
            "project_id":self.project.project_id,"title":title,"created_at":utc_now(),
            "master_format":"latex","source_verified":False,"patent_filing_authorized":False})
        return {"case_id":case_id,"manuscript_id":manuscript_id,"project_id":self.project.project_id,
                "format":"latex","sections":list(SECTIONS),
                "path_hint":"案卷私有 manuscripts/ 目录；不通过 MCP 暴露任意文件路径"}

    def _check(self,case_id:str,manuscript_id:str)->Path:
        folder=self._folder(case_id,manuscript_id)
        manifest=folder/"manuscript.json"
        if not manifest.is_file() or manifest.is_symlink():
            raise PatentWorkflowError("论文不存在。")
        value=json.loads(manifest.read_text(encoding="utf-8"))
        if value.get("project_id")!=self.project.project_id or value.get("case_id")!=case_id:
            raise PatentWorkflowError("论文项目归属不一致。")
        return folder

    def read(self,case_id:str,manuscript_id:str,section_key:str)->dict:
        folder=self._check(case_id,manuscript_id)
        if section_key!="references" and section_key not in SECTIONS:
            raise PatentWorkflowError("仅允许读取已登记章节或参考文献。")
        path=folder/("references.bib" if section_key=="references" else "sections/"+section_key+".tex")
        if path.is_symlink():
            raise PatentWorkflowError("文稿资源不得为符号链接。")
        blob=path.read_bytes()
        return {"section":section_key,"content":blob.decode("utf-8"),
                "sha256":sha256(blob).hexdigest()}

    def edit(self,case_id:str,manuscript_id:str,section_key:str,content:str)->dict:
        folder=self._check(case_id,manuscript_id)
        if section_key not in SECTIONS and section_key!="references":
            raise PatentWorkflowError("章节编号不在受控清单。")
        if section_key=="references":
            if not isinstance(content,str) or len(content)>150000 or _BAD.search(content) or _REMOTE.search(content):
                raise PatentWorkflowError("BibTeX 含危险宏、远程资源或文本超限。")
            if not content.strip().startswith(("@","%")):
                raise PatentWorkflowError("参考文献必须为 BibTeX 条目或注释。")
        else:
            _safe_section(content)
        name="references.bib" if section_key=="references" else "sections/"+section_key+".tex"
        path=folder/name
        if path.is_symlink():
            raise PatentWorkflowError("原稿路径被替换为符号链接。")
        content=content.rstrip()+"\n"
        digest=sha256(content.encode("utf-8")).hexdigest()
        with self.workspace.connect(write=True) as db:
            row=db.execute("""SELECT COALESCE(MAX(revision),0) AS max_revision
                FROM manuscript_versions WHERE case_id=? AND manuscript_id=? AND section_key=?""",
                (case_id,manuscript_id,section_key)).fetchone()
            revision=row["max_revision"]+1
            archive=folder/"versions"/f"{section_key}_v{revision:05d}.txt"
            if archive.exists():
                raise PatentWorkflowError("历史修订文件已存在，拒绝覆盖。")
            archive.write_text(content,encoding="utf-8")
            # 写入历史后原子替换现稿。
            target=path.with_name("."+path.name+"."+uuid4().hex+".tmp")
            target.write_text(content,encoding="utf-8")
            target.replace(path)
            db.execute("""INSERT INTO manuscript_versions
                (case_id,manuscript_id,section_key,revision,sha256,created_at,source_path)
                VALUES(?,?,?,?,?,?,?)""",
                (case_id,manuscript_id,section_key,revision,digest,utc_now(),archive.name))
        return {"manuscript_id":manuscript_id,"section":section_key,
                "revision":revision,"sha256":digest,"latex_source_saved":True}

    def revisions(self,case_id:str,manuscript_id:str,section_key:str)->list[dict]:
        self._check(case_id,manuscript_id)
        if section_key not in SECTIONS and section_key!="references":
            raise PatentWorkflowError("章节不存在。")
        with self.workspace.connect() as db:
            rows=db.execute("""SELECT revision,sha256,created_at FROM manuscript_versions
                WHERE case_id=? AND manuscript_id=? AND section_key=? ORDER BY revision DESC LIMIT 50""",
                (case_id,manuscript_id,section_key)).fetchall()
        return [dict(row) for row in rows]

    def export(self,case_id:str,manuscript_id:str,output_format:str)->dict:
        """仅 Pandoc 解析转换，绝不在公网 MCP 执行 TeX 宏或编译引擎。"""
        if output_format not in {"docx","html","md"}:
            raise PatentWorkflowError("MCP 仅允许 docx/html/md；PDF 编译应在离线受控沙箱完成。")
        folder=self._check(case_id,manuscript_id)
        executable=shutil.which("pandoc")
        if not executable:
            raise PatentWorkflowError("缺少 Pandoc。请安装官方开源转换器。")
        # 仅拼接已登记的章节，阻断任意 \input 路径和外部引用。
        parts=[]
        meta=json.loads((folder/"manuscript.json").read_text(encoding="utf-8"))
        for key,(heading,kind) in SECTIONS.items():
            text=(folder/"sections"/(key+".tex")).read_text(encoding="utf-8")
            _safe_section(text)
            parts.append(text)
        source=folder/"exports"/"manuscript_flattened.tex"
        source.write_text("\n\n".join(parts)+"\n",encoding="utf-8")
        suffix="markdown" if output_format=="md" else output_format
        out=folder/"exports"/("research-draft."+output_format)
        cmd=[executable,"--from=latex","--to="+suffix,str(source),
             "--output",str(out)]
        bib=folder/"references.bib"
        if bib.is_file() and re.search(r"@\w+\s*\{",bib.read_text(encoding="utf-8")):
            cmd.extend(["--citeproc","--bibliography",str(bib)])
        try:
            proc=subprocess.run(cmd,cwd=folder/"exports",capture_output=True,text=True,
                                timeout=75,check=False)
        except (subprocess.TimeoutExpired,OSError) as exc:
            raise PatentWorkflowError("Pandoc 转换超时或程序不可用。") from exc
        if proc.returncode!=0 or not out.is_file():
            raise PatentWorkflowError("Pandoc 转换失败："+proc.stderr[:350])
        return {"manuscript_id":manuscript_id,"format":output_format,
                "size_bytes":out.stat().st_size,
                "sha256":sha256(out.read_bytes()).hexdigest(),
                "source_format":"latex","pdf_compile_performed":False,
                "relative_file":"cases/"+case_id+"/manuscripts/"+manuscript_id+"/exports/"+out.name,
                "warning":"输出仍须检查格式和版权；DOCX 不自动等同于中国专利局官方递交书式。"}
