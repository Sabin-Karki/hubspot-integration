import json
import secrets
import base64
import asyncio
import httpx
import requests
import urllib.parse

from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
from integrations.integration_item import IntegrationItem
from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

CLIENT_ID = '26a56744-c34c-4845-a3b9-9ea0cc47e08e'
CLIENT_SECRET = '7496281b-d606-4eb7-a124-f6b1aae33c1b'
REDIRECT_URI = 'http://localhost:8000/integrations/hubspot/oauth2callback'

AUTHORIZATION_URL = 'https://app.hubspot.com/oauth/authorize'
TOKEN_URL = 'https://api.hubspot.com/oauth/v1/token'

# defining what  to request from hubspot
SCOPE = 'crm.objects.contacts.read crm.objects.companies.read crm.objects.deals.read'

async def authorize_hubspot(user_id, org_id):
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id
    }
    encoded_state = base64.urlsafe_b64encode(json.dumps(state_data).encode('utf-8')).decode('utf-8')

    encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe='')

    # saving state in redis for later verification to prevent csrf attack
    await add_key_value_redis(f'hubspot_state:{org_id}:{user_id}',json.dumps(state_data),expire=600)

    auth_url = (
        f'{AUTHORIZATION_URL}'
        f'?client_id={CLIENT_ID}'
        f'&redirect_uri={encoded_redirect}'
        f'&scope={SCOPE}'
        f'&state={encoded_state}'
    )
    return auth_url


# hubspot will redirect to this endpoint after login,need to handle extraction of code and verify state and exchange code for access token
async def oauth2callback_hubspot(request: Request):
    if request.query_params.get('error'):
        raise HTTPException(status_code=400,detail=request.query_params.get('error_description'))

    code = request.query_params.get('code')

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    encoded_state = request.query_params.get('state')
    state_data = json.loads(base64.urlsafe_b64decode(encoded_state).decode('utf-8'))

    

    # original state is the one generated and saved in redis and need to compare with the one redirecting to this endpoint to prevent csrf and user and org id is to know which org and user is trying to integrate hubspot and allow access to its data to this application . 
    
    original_state = state_data.get('state')
    user_id = state_data.get('user_id')
    org_id = state_data.get('org_id')
      
    # verifying state of redirect with the one saved in state 
    saved_state = await get_value_redis(f'hubspot_state:{org_id}:{user_id}')

    # if state does not match the one saved then it is a potential attack which is an exception 

    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400,detail='State does not match. ')

    async with httpx.AsyncClient() as client:
        response, _ = await asyncio.gather(
            client.post(
                TOKEN_URL,
                data={
                    'grant_type':'authorization_code',
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'redirect_uri': REDIRECT_URI,
                    'code':code,
                },
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                }
            ),
            delete_key_redis(f'hubspot_state:{org_id}:{user_id}'),
        )

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {response.text}")

        
    await add_key_value_redis(f'hubspot_credentials:{org_id}:{user_id}',json.dumps(response.json()),expire=600)

    close_window_script = """
    <html>
        <script>
            window.close();
         </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)


async def get_hubspot_credentials(user_id, org_id):
    credentials = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}') 
    if not credentials:
        raise HTTPException(status_code=400, detail='Hubspot credentials not found.please integrate hubspot first.')
    credentials = json.loads(credentials) 
    await delete_key_redis(f'hubspot_credentials:{org_id}:{user_id}')
    return credentials


def create_integration_item_metadata_object(response_json, item_type) -> IntegrationItem:
    properties = response_json.get('properties', {})
 
    if item_type == 'Contact':
        first = properties.get('firstname', '')
        last = properties.get('lastname', '')
        name = f'{first} {last}'.strip()
        name = name if name else properties.get('email', 'Unknown Contact')
 
    elif item_type == 'Company':
        name = properties.get('name', 'Unknown Company')
 
    elif item_type == 'Deal':
        name = properties.get('dealname', 'Unknown Deal')
 
    else:
        name = str(response_json.get('id', 'Unknown'))
 
    return IntegrationItem(
        id=str(response_json.get('id')) + '_' + item_type,
        type=item_type,
        name=name,
        creation_time=properties.get('createdate'),
        last_modified_time=properties.get('hs_lastmodifieddate'),
    )    


async def get_items_hubspot(credentials) -> list[IntegrationItem]:
    credentials = json.loads(credentials)
    access_token = credentials.get('access_token')
    headers = {'Authorization': f'Bearer {access_token}'}
    list_of_items = []

    endpoints = [
        ('https://api.hubspot.com/crm/v3/objects/contacts', 'Contact'),
        ('https://api.hubspot.com/crm/v3/objects/companies', 'Company'),
        ('https://api.hubspot.com/crm/v3/objects/deals', 'Deal'),
    ]

    for url,item_type in endpoints:
        response = requests.get(url,headers=headers)
        if response.status_code ==200:
            results=response.json().get('results',[])
            for item in results:
                list_of_items.append(create_integration_item_metadata_object(item,item_type))
    
    print(f'Fetched {len(list_of_items)} from Hubspot')
    for item in list_of_items:
        print(item.__dict__)

    return list_of_items