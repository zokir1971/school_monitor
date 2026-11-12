"""Editable Word export of the same authorized teacher/pupil HTML projection."""
import re
from io import BytesIO
from html.parser import HTMLParser
from urllib.parse import urlsplit,parse_qs

class ExportError(ValueError): pass

class Node:
    def __init__(self,tag='',attrs=()): self.tag=tag;self.attrs=dict(attrs);self.children=[]
    def text(self): return ''.join(c if isinstance(c,str) else c.text() for c in self.children)

class Tree(HTMLParser):
    def __init__(self): super().__init__();self.root=Node();self.stack=[self.root]
    def handle_starttag(self,tag,attrs):
        n=Node(tag,attrs);self.stack[-1].children.append(n)
        if tag not in {'img','br','meta','link','input','hr'}:
            if len(self.stack)>200: raise ExportError('Document nesting limit')
            self.stack.append(n)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag: self.stack=self.stack[:i];break
    def handle_data(self,data): self.stack[-1].children.append(data)

def nodes(node):
    yield node
    for c in node.children:
        if isinstance(c,Node):yield from nodes(c)

def image_key(node):
    key=parse_qs(urlsplit(node.attrs.get('src','')).query).get('object_key',[''])[0]
    if not re.fullmatch(r'question-bank/media/[1-9][0-9]*/[0-9a-f]{32}\.(?:png|jpg|webp)',key):
        raise ExportError('Unsupported image reference')
    return key

def parse(html):
    tree=Tree();tree.feed(html)
    main=next((n for n in nodes(tree.root) if n.tag=='main'),None)
    if main is None:raise ExportError('Document body missing')
    return main

def build(main,images,audience):
    try:
        from docx import Document
        from docx.shared import Mm,Pt,RGBColor
        from docx.oxml import parse_xml
        from latex2mathml.converter import convert as to_mathml
        from mathml2omml import convert as to_omml
    except ImportError as exc:raise ExportError('Install requirements_docx.txt') from exc
    doc=Document();section=doc.sections[0]
    section.page_width=Mm(210);section.page_height=Mm(297)
    section.top_margin=section.bottom_margin=section.left_margin=section.right_margin=Mm(10)
    normal=doc.styles['Normal'];normal.font.name='Arial';normal.font.size=Pt(10 if audience=='teacher' else 11)
    normal.paragraph_format.space_after=Pt(3);normal.paragraph_format.line_spacing=1.05
    for name in ('Title','Heading 1','Heading 2','Heading 3'):
        doc.styles[name].font.color.rgb=RGBColor(0,0,0)
        doc.styles[name].paragraph_format.space_before=Pt(5);doc.styles[name].paragraph_format.space_after=Pt(3)
    from docx.oxml.ns import qn
    for style in doc.styles:
        for border in list(style.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
    doc.styles['Title'].font.size=Pt(16)
    def formula(paragraph,latex):
        try:
            xml=to_omml(to_mathml(latex.strip()))
            if 'xmlns:m=' not in xml:xml=xml.replace('<m:oMath','<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"',1)
            equation=parse_xml(xml)
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
            # Transparent MathML wrappers are not visible Word boxes.
            for box in list(equation.iter(qn('m:box'))):
                parent=box.getparent();content=box.find(qn('m:e'))
                if parent is not None and content is not None:
                    index=parent.index(box)
                    for child in list(content):parent.insert(index,child);index+=1
                    parent.remove(box)
            for radical in equation.iter(qn('m:rad')):
                if radical.find(qn('m:deg')) is None:
                    props=radical.find(qn('m:radPr'))
                    if props is None:props=OxmlElement('m:radPr');radical.insert(0,props)
                    hidden=OxmlElement('m:degHide');hidden.set(qn('m:val'),'1');props.append(hidden)
                    radical.insert(1,OxmlElement('m:deg'))
            paragraph._p.append(equation)
        except Exception as exc:raise ExportError('Cannot convert a formula to Word; export stopped') from exc
    def inline(node,paragraph,bold=False):
        if isinstance(node,str):
            value=re.sub(r'\s+',' ',node)
            if value.strip():paragraph.add_run(value).bold=bold
            return
        if node.tag in {'script','style','nav','button','input'}:return
        if node.tag=='math-field':formula(paragraph,node.text());return
        if node.tag=='img':
            key=image_key(node)
            try:
                from PIL import Image
                data=images[key]
                with Image.open(BytesIO(data)) as im:
                    w,h=im.size
                    if w*h>40_000_000:raise ValueError('Image pixel limit')
                limit=64 if 'option' in node.attrs.get('class','') or 'answer' in node.attrs.get('class','') else 128
                width=min(limit,72*w/max(h,1))
                paragraph.add_run().add_picture(BytesIO(data),width=Mm(width))
            except Exception as exc:raise ExportError('Cannot embed an image; export stopped') from exc
            return
        if node.tag=='br':paragraph.add_run().add_break();return
        if 'qb-render-response-placeholder' in node.attrs.get('class',''):return
        if node.tag=='select':
            for i,c in enumerate(node.children):
                if isinstance(c,Node) and c.tag=='option':
                    if i:paragraph.add_run(' / ')
                    inline(c,paragraph,bold)
            return
        preserve=('qb-segment-text' in node.attrs.get('class','') or 'data-readable-math-prose' in node.attrs)
        for position,c in enumerate(node.children):
            if position and isinstance(c,Node):paragraph.add_run(' ')
            if preserve and isinstance(c,str):
                # Explicit author line breaks, not whitespace from surrounding Jinja macros.
                for i,line in enumerate(c.splitlines()):
                    if i:paragraph.add_run().add_break()
                    inline(line,paragraph,bold or node.tag in {'strong','b'})
            else:inline(c,paragraph,bold or node.tag in {'strong','b'})
    blocks={'p','h1','h2','h3','h4','div','section','article','header','ol','ul','li','table','thead','tbody','tfoot','tr','td','th'}
    def visit(node):
        if isinstance(node,str):return
        if node.tag in {'script','style','nav'}:return
        if any(name in node.attrs.get('class','').split() for name in ('qb-render-option','qb-answer-item','qb-grading-row','document-open-part')):
            paragraph=doc.add_paragraph();inline(node,paragraph);return
        children=[c for c in node.children if isinstance(c,Node)]
        if node.tag in {'h1','h2','h3','h4'}:
            paragraph=doc.add_paragraph(style='Title' if node.tag=='h1' else 'Heading 2');inline(node,paragraph);return
        if not any(c.tag in blocks for c in children):
            if node.text().strip() or any(c.tag=='img' for c in nodes(node)):
                paragraph=doc.add_paragraph();inline(node,paragraph)
            return
        pending=[]
        def flush():
            if any((c.strip() if isinstance(c,str) else c.text().strip() or c.tag=='img') for c in pending):
                para=doc.add_paragraph()
                for c in pending:inline(c,para)
            pending.clear()
        for index,c in enumerate(node.children):
            if isinstance(c,Node) and c.tag in blocks:
                flush()
                if node.tag in {'ol','ul'} and c.tag=='li':
                    marker=sum(isinstance(x,Node) and x.tag=='li' for x in node.children[:index])+1
                    para=doc.add_paragraph();para.add_run(str(marker)+') ');inline(c,para)
                else:visit(c)
            else:pending.append(c)
        flush()
    visit(main)
    output=BytesIO();doc.save(output);return output.getvalue()

async def export(html,audience):
    import asyncio
    main=parse(html)
    keys=sorted({image_key(n) for n in nodes(main) if n.tag=='img'})
    if len(keys)>100:raise ExportError('Too many images for one export')
    images={};total=0
    if keys:
        from app.core.storage.factory import get_storage
        storage=get_storage()
        for key in keys:
            try:data=await storage.read(object_key=key,max_bytes=8_000_000)
            except Exception as exc:raise ExportError('Cannot load an image from storage') from exc
            total+=len(data)
            if total>32_000_000:raise ExportError('Image total exceeds export limit')
            images[key]=data
    return await asyncio.to_thread(build,main,images,audience)
