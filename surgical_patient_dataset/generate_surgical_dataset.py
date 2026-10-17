import csv,random,json,zipfile,os,collections
from datetime import date,timedelta
R=random.Random(5724)
OUT='/mnt/data/surgical_patient_dataset'; os.makedirs(OUT,exist_ok=True)
procedures=[('Laparoscopic Cholecystectomy','General OR','PACU'),('Radical Mastectomy','Oncology OR','Surgical ward'),('Knee Arthroscopy','Ambulatory OR','PACU'),('Ureteroscopy with Stent Placement','Urology OR','PACU'),('Coronary Artery Bypass Graft','Cardiac OR','Cardiac ICU')]
conditions=['Hypertension','Type 2 diabetes mellitus','Hyperlipidemia','Asthma','Obstructive sleep apnea','Chronic kidney disease','Anemia','COPD','Atrial fibrillation','Hypothyroidism','Gastroesophageal reflux disease']
indications=['Symptomatic cholelithiasis','Breast malignancy','Meniscal tear','Ureteral calculus','Multivessel coronary artery disease']
medmap={'Hypertension':'Lisinopril','Type 2 diabetes mellitus':'Metformin','Hyperlipidemia':'Atorvastatin','Asthma':'Albuterol','Obstructive sleep apnea':'None recorded','Chronic kidney disease':'None recorded','Anemia':'Ferrous sulfate','COPD':'Tiotropium','Atrial fibrillation':'Apixaban','Hypothyroidism':'Levothyroxine','Gastroesophageal reflux disease':'Omeprazole'}
prior=['Appendectomy','Hernia repair','Cesarean section','Hysterectomy','Tonsillectomy','Knee arthroscopy','Cataract surgery','Cholecystectomy']
fields={
'patients.csv':['patient_id','age','sex','diagnoses','medical_history','allergies','anesthesia_complication_history'],
'surgical_cases.csv':['surgery_id','patient_id','scheduled_surgery','surgery_date','surgery_location','procedure','postoperative_location','cardiology_clearance','ekg_completed','ekg_date','ekg_interpretation','consent_completed','required_labs_completed','blood_products_available','preoperative_status'],
'past_surgeries.csv':['history_id','patient_id','prior_procedure','procedure_year','prior_anesthesia_issue'],
'medications.csv':['medication_id','patient_id','medication_name','dose','frequency','status'],
'lab_results.csv':['lab_id','surgery_id','patient_id','test_name','result_value','unit','reference_low','reference_high','collection_date','result_status'],
'diagnostic_tests.csv':['test_id','surgery_id','patient_id','test_type','completed','test_date','interpretation','status'],
'imaging.csv':['imaging_id','surgery_id','patient_id','imaging_type','imaging_date','report','status'],
'clearances.csv':['clearance_id','surgery_id','patient_id','clearance_type','applicability','status','assessment_date','assessment_note'],
'consents.csv':['consent_id','surgery_id','patient_id','consent_type','applicability','status','signed_date'],
'blood_products.csv':['blood_record_id','surgery_id','patient_id','abo_rh','antibody_screen','crossmatch_status','product_type','units_available','requirement_status'],
'clinical_notes.csv':['note_id','surgery_id','patient_id','note_type','note_date','note_text'],
'procedure_requirements.csv':['requirement_id','procedure','item_type','item_name','applicability','rule_description','source'],
'ground_truth.csv':['surgery_id','patient_id','scenario','expected_outstanding_items','expected_review_items','expected_preoperative_status','evidence_ids']}
rows={k:[] for k in fields}
def add(fn,**kwargs):
 row={k:kwargs.get(k,'') for k in fields[fn]}; rows[fn].append(row);return row
reqs={
'Laparoscopic Cholecystectomy':['Hemoglobin','Surgery consent','Anesthesia consent','H&P note'],
'Radical Mastectomy':['Hemoglobin','Surgery consent','Anesthesia consent','H&P note'],
'Knee Arthroscopy':['Surgery consent','Anesthesia consent','H&P note'],
'Ureteroscopy with Stent Placement':['Creatinine','Urine culture','Surgery consent','Anesthesia consent','H&P note'],
'Coronary Artery Bypass Graft':['Hemoglobin','Creatinine','Platelets','INR','EKG','Cardiology assessment','Surgery consent','Anesthesia consent','Blood consent','Crossmatched red cells','H&P note']}
for proc,items in reqs.items():
 for item in items:
  kind='lab' if item in ['Hemoglobin','Creatinine','Platelets','INR','Urine culture'] else ('consent' if 'consent' in item else 'diagnostic' if item=='EKG' else 'clearance' if 'assessment' in item else 'note' if 'note' in item else 'blood')
  add('procedure_requirements.csv',requirement_id=f'R{len(rows["procedure_requirements.csv"])+1:03d}',procedure=proc,item_type=kind,item_name=item,applicability='Required in synthetic teaching scenario',rule_description='Documented and dated before surgery; no universal clinical clearance implied',source='Synthetic educational project rule (not clinical guideline)')
labinfo={'Hemoglobin':(13.2,'g/dL',12,17.5),'Creatinine':(1.0,'mg/dL',0.6,1.3),'Platelets':(220,'10^3/uL',150,400),'INR':(1.0,'ratio',0.8,1.2),'HbA1c':(6.7,'%',4,5.7),'Urine culture':('No growth','text','','')}
for j,(proc,location,postop) in enumerate(procedures):
 for n in range(20):
  idx=j*20+n+1; pid=f'P{idx:03d}'; sid=f'S{idx:03d}'; surgery_date=date(2026,11,12)+timedelta(days=(idx-1)%26)
  age=R.randint(18,90); sex=R.choice(['Female','Male']); diag=[indications[j]]+R.sample(conditions,k=R.choices([0,1,2,3],[15,35,35,15])[0]);
  if proc=='Radical Mastectomy': sex='Female'
  allergy=R.choice(['No known drug allergies','No known drug allergies','Penicillin','Latex','Sulfonamides'])
  issue=R.choice(['None documented']*9+['Prior postoperative nausea and vomiting'])
  add('patients.csv',patient_id=pid,age=age,sex=sex,diagnoses='; '.join(diag),medical_history='; '.join(diag),allergies=allergy,anesthesia_complication_history=issue)
  past=R.sample(prior,k=R.choices([0,1,2,3],[40,35,20,5])[0]);
  for pp in past:
   add('past_surgeries.csv',history_id=f'PS{len(rows["past_surgeries.csv"])+1:04d}',patient_id=pid,prior_procedure=pp,procedure_year=R.randint(max(1995,2026-age+15),2024),prior_anesthesia_issue=issue)
  for cond in diag:
   med=medmap.get(cond)
   if med and med!='None recorded' and med not in [x['medication_name'] for x in rows['medications.csv'] if x['patient_id']==pid]:
    add('medications.csv',medication_id=f'M{len(rows["medications.csv"])+1:04d}',patient_id=pid,medication_name=med,dose='See synthetic medication list',frequency='As documented',status='Active')
  scenario=['complete','missing_consent','missing_lab','outdated_test','clinical_review','conflicting_documentation'][n%6]
  missing=[]; review=[]; evid=[]; labdates={}; lab_present={};
  required=reqs[proc]; labnames=set(['Hemoglobin','Creatinine','Platelets','INR','Urine culture','HbA1c'] if proc=='Coronary Artery Bypass Graft' else ['Hemoglobin','Creatinine','Platelets','HbA1c','Urine culture'])
  for test in labnames:
   if test not in required and R.random()>.48:continue
   if scenario=='missing_lab' and test==next((t for t in required if t in labinfo),''):continue
   dt=surgery_date-timedelta(days=(110 if scenario=='outdated_test' and test==next((t for t in required if t in labinfo),'') else R.randint(2,15)))
   base,unit,lo,hi=labinfo[test]
   val=base if isinstance(base,str) else round(base*(R.uniform(.8,1.2)),2)
   if scenario=='clinical_review' and test=='Hemoglobin':val=8.7;review.append('Hemoglobin result requires clinician review')
   if scenario=='clinical_review' and test=='Creatinine' and 'Hemoglobin' not in labnames:val=2.4;review.append('Creatinine result requires clinician review')
   labid=f'L{len(rows["lab_results.csv"])+1:04d}'; labdates[test]=dt;lab_present[test]=True
   add('lab_results.csv',lab_id=labid,surgery_id=sid,patient_id=pid,test_name=test,result_value=val,unit=unit,reference_low=lo,reference_high=hi,collection_date=dt.isoformat(),result_status='Final')
   evid.append(labid)
  for test in required:
   if test in labinfo:
    if test not in lab_present:missing.append(f'{test} result not documented')
    elif (surgery_date-labdates[test]).days>90:missing.append(f'{test} result outside synthetic 90-day documentation window')
  ekg_app=proc=='Coronary Artery Bypass Graft' or R.random()<.35
  ekg_dt=surgery_date-timedelta(days=R.randint(1,14)) if ekg_app else None
  if scenario=='outdated_test' and proc=='Coronary Artery Bypass Graft':ekg_dt=surgery_date-timedelta(days=120)
  ekg_interp=R.choice(['Normal sinus rhythm','Sinus rhythm; nonspecific ST-T changes','Atrial fibrillation']) if ekg_app else ''
  if ekg_app:
   tid=f'T{len(rows["diagnostic_tests.csv"])+1:04d}';evid.append(tid)
   add('diagnostic_tests.csv',test_id=tid,surgery_id=sid,patient_id=pid,test_type='EKG',completed='Yes',test_date=ekg_dt.isoformat(),interpretation=ekg_interp,status='Final')
   if proc=='Coronary Artery Bypass Graft' and (surgery_date-ekg_dt).days>90:missing.append('EKG outside synthetic 90-day documentation window')
  for kind in ['Cardiology','Pulmonary']:
   applicable=kind=='Cardiology' and proc=='Coronary Artery Bypass Graft'
   cid=f'C{len(rows["clearances.csv"])+1:04d}'
   add('clearances.csv',clearance_id=cid,surgery_id=sid,patient_id=pid,clearance_type=kind+' assessment',applicability='Required in synthetic scenario' if applicable else 'Not indicated in synthetic scenario',status='Documented' if applicable else 'Not applicable',assessment_date=(surgery_date-timedelta(days=5)).isoformat() if applicable else '',assessment_note='Fictional documentation record; not a medical clearance decision' if applicable else '')
   if applicable:evid.append(cid)
  consents={};
  for ctype in ['Surgery consent','Anesthesia consent','Blood consent']:
   applicable=ctype!='Blood consent' or proc=='Coronary Artery Bypass Graft'
   missing_this=scenario=='missing_consent' and ctype=='Anesthesia consent'
   status=('Not applicable' if not applicable else 'Missing' if missing_this else 'Signed')
   cid=f'CO{len(rows["consents.csv"])+1:04d}'; consents[ctype]=status
   add('consents.csv',consent_id=cid,surgery_id=sid,patient_id=pid,consent_type=ctype,applicability='Required in synthetic scenario' if applicable else 'Not indicated',status=status,signed_date=(surgery_date-timedelta(days=3)).isoformat() if status=='Signed' else '')
   if applicable:evid.append(cid)
   if missing_this:missing.append('Anesthesia consent not documented')
  bloodreq=proc=='Coronary Artery Bypass Graft'
  add('blood_products.csv',blood_record_id=f'B{idx:03d}',surgery_id=sid,patient_id=pid,abo_rh=R.choice(['O+','A+','B+','AB+','O-','A-']),antibody_screen='Negative' if bloodreq else 'Not performed',crossmatch_status='Completed' if bloodreq else 'Not required',product_type='Packed red blood cells' if bloodreq else 'Not required',units_available=2 if bloodreq else 0,requirement_status='Available' if bloodreq else 'Not required')
  add('imaging.csv',imaging_id=f'I{idx:03d}',surgery_id=sid,patient_id=pid,imaging_type='Chest X-ray' if proc=='Coronary Artery Bypass Graft' else 'Procedure-related imaging',imaging_date=(surgery_date-timedelta(days=9)).isoformat(),report='No acute findings reported' if proc=='Coronary Artery Bypass Graft' else 'Relevant imaging report documented',status='Final')
  if scenario=='conflicting_documentation':review.append('Clinical note conflicts with structured consent record')
  note_text=(f'{age}-year-old {sex.lower()} patient scheduled for {proc} on {surgery_date.isoformat()}. '
             f'Medical history: {"; ".join(diag)}. Prior procedures: {"; ".join(past) if past else "none documented"}. '
             f'Allergies: {allergy}. '
             f'Surgery consent: {consents["Surgery consent"]}. Anesthesia consent: '
             f'{"Signed" if scenario=="conflicting_documentation" else consents["Anesthesia consent"]}. '
             f'Laboratory records and diagnostic studies should be checked against the structured record.')
  noteid=f'N{idx:03d}'
  add('clinical_notes.csv',note_id=noteid,surgery_id=sid,patient_id=pid,note_type='Preoperative H&P',note_date=(surgery_date-timedelta(days=2)).isoformat(),note_text=note_text)
  evid.append(noteid)
  if scenario=='conflicting_documentation':
   # deliberately contradict the structured note for evaluation
   rows['clinical_notes.csv'][-1]['note_text']=note_text.replace('Surgery consent: Signed','Surgery consent: Missing')
  if scenario=='clinical_review' and not review:review.append('Clinical findings require clinician review')
  status='Outstanding requirements' if missing else 'Needs clinical review' if review else 'Documentation complete'
  add('surgical_cases.csv',surgery_id=sid,patient_id=pid,scheduled_surgery=proc,surgery_date=surgery_date.isoformat(),surgery_location=location+' '+str((n%4)+1),procedure=proc+(' (3-vessel bypass)' if proc=='Coronary Artery Bypass Graft' else ''),postoperative_location=postop,cardiology_clearance='Documented' if bloodreq else 'Not indicated in synthetic scenario',ekg_completed='Yes' if ekg_app else 'Not indicated',ekg_date=ekg_dt.isoformat() if ekg_dt else '',ekg_interpretation=ekg_interp,consent_completed='Yes' if all(v in ('Signed','Not applicable') for v in consents.values()) else 'No',required_labs_completed='No' if any('result' in x.lower() for x in missing) else 'Yes',blood_products_available='Yes' if bloodreq else 'Not required',preoperative_status=status)
  add('ground_truth.csv',surgery_id=sid,patient_id=pid,scenario=scenario,expected_outstanding_items=' | '.join(missing),expected_review_items=' | '.join(review),expected_preoperative_status=status,evidence_ids=' | '.join(evid))
for fn,records in rows.items():
 with open(os.path.join(OUT,fn),'w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields[fn]);w.writeheader();w.writerows(records)
readme='''# Surgical Patient Preparedness — Fully Synthetic Dataset\n\n100 fictional adult patients (18–90), 20 cases per procedure: laparoscopic cholecystectomy, radical mastectomy, knee arthroscopy, ureteroscopy with stent placement, and coronary artery bypass graft.\n\n## Data layout\n- `patients.csv`: demographics, diagnoses, history, allergies\n- `surgical_cases.csv`: one master overview per case (100 cases)\n- `past_surgeries.csv`: zero or more previous procedures per patient\n- `medications.csv`: synthetic active medication records\n- `lab_results.csv`: dated laboratory results (missing tests represented by absent rows)\n- `diagnostic_tests.csv`: dated EKG results when present\n- `imaging.csv`: text interpretations only, not real medical images\n- `clearances.csv`: fictional assessment documentation\n- `consents.csv`: each consent's applicability and status\n- `blood_products.csv`: fictional blood availability data\n- `clinical_notes.csv`: fictional H&P text\n- `procedure_requirements.csv`: illustrative teaching-case requirements, **NOT clinical guidelines**\n- `ground_truth.csv`: case-level expected missing/review items for evaluation\n\nJoin using `patient_id` and, for case-specific records, `surgery_id`. `ground_truth.csv` should be hidden from the AI during inference.\n\n## Important caveats\nAll data are fictional. Do not use for patient care or actual surgical clearance. The requirements (including a 90-day demonstration window for dated tests) are arbitrary educational rules, **not evidence-based clinical criteria**. Status means *documentation review status*, never clinical fitness for surgery. For actual clinical application, obtain clinician-approved institution-specific requirements.\n\n## Reproducibility\nThe archive includes `generate_surgical_dataset.py`, which uses only the Python standard library and a fixed random seed. Run `python generate_surgical_dataset.py` from a folder with write access (the script's output path can be changed).\n\n## Development suggestion\nUse 80 cases for development and hold out 20 for evaluation, stratifying by procedure and scenario. Validate structured records independently of narrative notes.\n'''
open(os.path.join(OUT,'README.md'),'w').write(readme)
assert len(rows['patients.csv'])==100 and len(rows['surgical_cases.csv'])==100 and len(rows['ground_truth.csv'])==100
assert collections.Counter(x['scheduled_surgery'] for x in rows['surgical_cases.csv'])==dict((p[0],20) for p in procedures)
with zipfile.ZipFile('/mnt/data/surgical_patient_dataset.zip','w',zipfile.ZIP_DEFLATED) as z:
 for fn in os.listdir(OUT):z.write(os.path.join(OUT,fn),arcname='surgical_patient_dataset/'+fn)
 z.write(__file__,arcname='surgical_patient_dataset/generate_surgical_dataset.py')
print({k:len(v) for k,v in rows.items()})
print('/mnt/data/surgical_patient_dataset.zip')
