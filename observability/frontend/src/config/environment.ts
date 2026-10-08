const required = (name: keyof ImportMetaEnv): string => {
  const value = import.meta.env[name]
  if (!value) {
    throw new Error(`Missing frontend environment variable: ${name}`)
  }
  return value
}

export const environment = {
  apiUrl: required('VITE_OBSERVABILITY_API_URL'),
  cognitoIssuer: required('VITE_COGNITO_ISSUER'),
  cognitoClientId: required('VITE_COGNITO_CLIENT_ID'),
  redirectUri: import.meta.env.VITE_COGNITO_REDIRECT_URI ?? `${window.location.origin}/auth/callback`,
  logoutUri: import.meta.env.VITE_COGNITO_LOGOUT_URI ?? `${window.location.origin}/`,
}
