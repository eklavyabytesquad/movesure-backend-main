from dotenv import load_dotenv; load_dotenv()
from app.services.utils.supabase import get_client
from app.services.ewaybill.settings_service import get_company_gstin
from app.services.ewaybill.records_service import fetch_ewaybill

db = get_client()
COMPANY_ID = '815fcdb9-c36b-4288-9ed3-8210eaf40332'
BRANCH_ID  = '0c15b4c4-3d14-4c68-af43-c8ce7e738fd7'
USER_ID    = 'ab10fcbb-eb8e-434a-8272-ca1991bbfaed'
gstin = get_company_gstin(COMPANY_ID)

for ewb_num in ['461719118240', '411719918744']:
    print(f"\n{'='*50}")
    print(f"EWB: {ewb_num}")
    try:
        result = fetch_ewaybill(
            ewb_num, gstin,
            company_id=COMPANY_ID, branch_id=BRANCH_ID,
            user_id=USER_ID, force_refresh=True
        )
        print('source          :', result.get('source'))
        print('ewb_record_id   :', result.get('ewb_record_id'))
        print('total_valid     :', result.get('total_validations'))
        print('latest_status   :', result.get('latest_nic_status'))

        nic_data = result.get('data', {})
        msg = nic_data.get('results', {}).get('message', {})
        print('eway_bill_status:', msg.get('eway_bill_status'))
        print('eway_bill_valid :', msg.get('eway_bill_valid_date'))
        print('vehicle_type    :', msg.get('vehicle_type'))
        print('transporter     :', msg.get('transporter_name'))

        rec = db.table('ewb_records').select(
            'ewb_id,ewb_status,valid_upto,vehicle_number,vehicle_type,transporter_id,raw_response'
        ).eq('company_id', COMPANY_ID).eq('eway_bill_number', ewb_num).maybe_single().execute()
        if rec.data:
            r = rec.data
            print('DB vehicle_type :', r.get('vehicle_type'))
            print('DB valid_upto   :', r.get('valid_upto'))
            print('DB raw_response :', 'POPULATED' if r.get('raw_response') else 'EMPTY')
        else:
            print('DB: NO RECORD')

        log = db.table('ewb_validation_log').select(
            'version_no,nic_status,valid_upto,triggered_by,validated_at'
        ).eq('company_id', COMPANY_ID).eq('eway_bill_number', ewb_num).order('version_no', desc=True).limit(1).execute()
        if log.data:
            r = log.data[0]
            print('LOG v' + str(r['version_no']) + ': status=' + str(r.get('nic_status')) + ' valid_upto=' + str(r.get('valid_upto')) + ' at=' + str(r.get('validated_at')))
        else:
            print('LOG: NO ROWS')

    except Exception as e:
        print('ERROR:', type(e).__name__, str(e)[:300])
