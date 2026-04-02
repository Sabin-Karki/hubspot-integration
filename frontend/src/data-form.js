import { useState } from 'react';
import {
    Box,
    TextField,
    Button,
} from '@mui/material';
import axios from 'axios';

const endpointMapping = {
    'Notion': 'notion',
    'Airtable': 'airtable',
    'HubSpot': 'hubspot',
};

export const DataForm = ({ integrationType, credentials }) => {
    const [loadedData, setLoadedData] = useState(null);
    const endpoint = endpointMapping[integrationType];

    if (!endpoint) {
        console.error('Invalid integration type:', integrationType);
        return <div style={{ color: 'red' }}>Invalid integration type</div>;
    }

    const handleLoad = async () => {
        try {
            console.log('Loading data for endpoint:', endpoint, 'with credentials:', credentials);
            const formData = new FormData();
            formData.append('credentials', JSON.stringify(credentials));
            const response = await axios.post(`http://localhost:8000/integrations/${endpoint}/get_hubspot_items`, formData);
            setLoadedData(JSON.stringify(response.data, null, 2)); // formatted JSON
        } catch (e) {
            console.error(e);
            alert(e?.response?.data?.detail || 'Failed to load data');
        }
    }

    return (
        <Box display='flex' justifyContent='center' alignItems='center' flexDirection='column' width='100%'>
            <Box display='flex' flexDirection='column' width='100%'>
                <TextField
                    label="Loaded Data"
                    value={loadedData || ''}
                    sx={{mt: 2}}
                    InputLabelProps={{ shrink: true }}
                    disabled
                    multiline
                    rows={10}
                />
                <Button
                    onClick={handleLoad}
                    sx={{mt: 2}}
                    variant='contained'
                >
                    Load Data
                </Button>
                <Button
                    onClick={() => setLoadedData(null)}
                    sx={{mt: 1}}
                    variant='contained'
                    color='secondary'
                >
                    Clear Data
                </Button>
            </Box>
        </Box>
    );
}