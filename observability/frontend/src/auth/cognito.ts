import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts'
import { environment } from '../config/environment'

const userManager = new UserManager({
  authority: environment.cognitoIssuer,
  client_id: environment.cognitoClientId,
  redirect_uri: environment.redirectUri,
  post_logout_redirect_uri: environment.logoutUri,
  response_type: 'code',
  scope: 'openid email profile',
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  revokeTokensOnSignout: true,
  revokeTokenTypes: ['refresh_token'],
})

const REQUIRED_GROUP = 'observability-readonly'

const decodeAccessToken = (accessToken: string): Record<string, unknown> | null => {
  try {
    const encodedPayload = accessToken.split('.')[1]
    const base64 = encodedPayload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
    return JSON.parse(atob(padded)) as Record<string, unknown>
  } catch {
    return null
  }
}

export const hasRequiredGroup = (accessToken: string): boolean => {
  const claims = decodeAccessToken(accessToken)
  const groups = claims?.['cognito:groups']
  return Array.isArray(groups) && groups.includes(REQUIRED_GROUP)
}

export const signIn = (selectAccount = false): Promise<void> =>
  userManager.signinRedirect(
    selectAccount ? { extraQueryParams: { prompt: 'select_account' } } : undefined,
  )

export const completeSignIn = (): Promise<User> => userManager.signinRedirectCallback()

export const signOut = (): Promise<void> =>
  userManager.signoutRedirect({
    extraQueryParams: {
      client_id: environment.cognitoClientId,
      logout_uri: environment.logoutUri,
    },
  })

export const removeCurrentUser = (): Promise<void> => userManager.removeUser()

export const getCurrentUser = (): Promise<User | null> => userManager.getUser()
