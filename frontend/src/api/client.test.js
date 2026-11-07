import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import { apiFetch, setAccessToken, setRefreshHandler, setUnauthorizedHandler } from './client'
const unauthorized = () => new Response(JSON.stringify({error:{code:'unauthorized',message:'expired'}}), {status:401,headers:{'Content-Type':'application/json'}})
beforeEach(() => { setAccessToken('synthetic-old'); setRefreshHandler(null); setUnauthorizedHandler(null) })
afterEach(() => vi.unstubAllGlobals())
it('does not invalidate a newer session when an old request returns 401', async () => {
  let release
  vi.stubGlobal('fetch', vi.fn(() => new Promise(r => { release = r })))
  const invalidate = vi.fn(); setUnauthorizedHandler(invalidate)
  const pending = apiFetch('/vault'); setAccessToken('synthetic-new'); release(unauthorized())
  await expect(pending).rejects.toThrow('expired')
  expect(invalidate).not.toHaveBeenCalled()
})
it('does not refresh or clear a valid session for rejected reauthentication input', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({error:{code:'invalid_credentials',message:'wrong password'}}), {status:401})))
  const refresh = vi.fn(), invalidate = vi.fn(); setRefreshHandler(refresh); setUnauthorizedHandler(invalidate)
  await expect(apiFetch('/auth/change-password',{method:'POST',body:{}})).rejects.toThrow('wrong password')
  expect(refresh).not.toHaveBeenCalled(); expect(invalidate).not.toHaveBeenCalled()
})
