import React from 'react';
import {render, screen, fireEvent, waitFor, cleanup} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {vi, afterEach, test, expect} from 'vitest';
import App from './App.jsx';
afterEach(()=>{cleanup();localStorage.clear();vi.restoreAllMocks();});
test('asks for approval and sends the human decision separately',async()=>{
 localStorage.setItem('demobank-run','abc');
 global.fetch=vi.fn(async (url,options)=>({ok:true,json:async()=>url.endsWith('/health')?{mode:'demo'}:url.endsWith('/decision')?{approved:true}:{status:'AWAITING_APPROVAL',events:[],case:null}}));
 render(<App/>);
 const approve=await screen.findByRole('button',{name:'Approve & create case'});
 expect(fetch.mock.calls.some(([u])=>u.endsWith('/decision'))).toBe(false);
 fireEvent.click(approve);
 await waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/reviews/abc/decision',expect.objectContaining({body:JSON.stringify({approved:true,reviewer:'Demo Reviewer'})})));
});
test('shows a readable connection error',async()=>{
 global.fetch=vi.fn(async()=>{throw new Error('Backend unavailable');});
 render(<App/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable');
});
