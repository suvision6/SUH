// Fixed local workbook adapter. Existing dependency runtime is provided by caller.
import fs from 'node:fs/promises';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';
const [baselinePath,out,render] = process.argv.slice(2);
const b=JSON.parse(await fs.readFile(baselinePath,'utf8'));
const workbook=Workbook.create();
const review=workbook.worksheets.add('Review');
const source=workbook.worksheets.add('Sources');
const metadata=workbook.worksheets.add('Baseline');
const headers=['单元ID','片段ID','来源ID','估时/条件（只列一次）','完整正文（可修改）','审阅意见（不改正文）'];
review.mergeCells('A1:F1'); review.getRange('A1').values=[[b.title]];
review.mergeCells('A2:F2'); review.getRange('A2').values=[['按稳定ID回流；续行不是镜头。正文修改与意见分开。保存文件不等于批准。']];
review.getRange('A3:F3').values=[headers];
const rows=b.segments.map(s=>[s.item_id,s.id,s.source_ids.join(', '),s.timing_note,s.body,'']);
review.getRange(`A4:F${rows.length+3}`).setNumberFormat('@');
review.getRange(`A4:F${rows.length+3}`).values=rows;
review.getRange(`A1:F${rows.length+3}`).format.font={name:'PingFang SC',size:11,color:'#203632'};
review.getRange(`A1:F${rows.length+3}`).format.wrapText=true;
review.getRange(`A1:F${rows.length+3}`).format.verticalAlignment='top';
review.getRange('A1:F1').format={fill:'#174D44',font:{name:'PingFang SC',size:17,bold:true,color:'#FFFFFF'},rowHeight:36};
review.getRange('A2:F2').format.rowHeight=32;
review.getRange('A3:F3').format={fill:'#E2ECE8',font:{name:'PingFang SC',size:11,bold:true},rowHeight:32};
for(const [col,width] of [['A',95],['B',130],['C',100],['D',170],['E',455],['F',270]]) review.getRange(`${col}:${col}`).format.columnWidthPx=width;
for(let i=0;i<rows.length;i++){
  const row=review.getRange(`A${i+4}:F${i+4}`);
  row.format.fill=i%2===0?'#FFFFFF':'#F5F8F6';
  // Conservative line estimate for 455 px, 11 pt CJK text; never shrink fonts.
  const lines=rows[i][4].split('\n').reduce((sum,line)=>sum+Math.max(1,Math.ceil(Array.from(line).reduce((n,c)=>n+(c.charCodeAt(0)>255?2:1),0)/58)),0);
  row.format.rowHeight=Math.max(54,Math.min(380,lines*18+18));
  review.getRange(`F${i+4}`).format.fill='#FFF6D9';
}
review.freezePanes.freezeRows(3);
review.tables.add(`A3:F${rows.length+3}`,true,'ReviewUnits');
source.getRange('A1:C1').values=[['来源ID','来源片段ID','来源原文（只读；修改来源请另行说明）']];
source.getRange(`A2:C${b.source_segments.length+1}`).setNumberFormat('@');
source.getRange(`A2:C${b.source_segments.length+1}`).values=b.source_segments.map(s=>[s.source_id,s.id,s.text]);
source.getRange(`A1:C${b.source_segments.length+1}`).format.font={name:'PingFang SC',size:11,color:'#203632'};
source.getRange(`A1:C${b.source_segments.length+1}`).format.wrapText=true;
source.getRange(`A1:C${b.source_segments.length+1}`).format.verticalAlignment='top';
source.getRange('A:A').format.columnWidthPx=110;source.getRange('B:B').format.columnWidthPx=135;source.getRange('C:C').format.columnWidthPx=700;
source.getRange('A1:C1').format={fill:'#E2ECE8',font:{bold:true},rowHeight:32};
for(let i=0;i<b.source_segments.length;i++) source.getRange(`A${i+2}:C${i+2}`).format.rowHeight=Math.min(390,Math.max(56,b.source_segments[i].text.split('\n').reduce((n,t)=>n+Math.max(1,Math.ceil(t.length/40)),0)*18+18));
source.freezePanes.freezeRows(1);
metadata.getRange('A1:B4').values=[['field','value'],['baseline_sha256',b.baseline_sha256],['format','suh-review-baseline/1'],['status','候选审阅；任何保存和自检均不自动采用']];
metadata.getRange('A:A').format.columnWidthPx=190;metadata.getRange('B:B').format.columnWidthPx=600;
metadata.getRange('A1:B4').format.font={name:'PingFang SC',size:11};metadata.getRange('A1:B4').format.rowHeight=30;
metadata.getRange('A1:B1').format.fill='#E2ECE8';
for(const sheet of [review,source,metadata]) sheet.showGridLines=false;
const file=await SpreadsheetFile.exportXlsx(workbook);await file.save(`${out}/Review.xlsx`);
if(render==='--render'){
  for(const [sheetName,range] of [['Review',`A1:F${Math.min(6,rows.length+3)}`],['Sources',`A1:C${Math.min(4,b.source_segments.length+1)}`],['Baseline','A1:B4']]){
    const preview=await workbook.render({sheetName,range,scale:1,format:'png'});
    await fs.writeFile(`${out}/${sheetName}-preview.png`,new Uint8Array(await preview.arrayBuffer()));
  }
}
