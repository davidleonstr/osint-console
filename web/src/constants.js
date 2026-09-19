// Fixed column order for the agreement matrix. Kept stable so a filled square
// always means the same scanner regardless of which ones ran.
export const ORDER = ['sherlock', 'maigret', 'holehe', 'blackbird'];

export const EMAIL = /^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i;
export const HANDLE = /^[A-Za-z0-9._-]{1,64}$/;

export const kindOf = (value) => (EMAIL.test(value.trim()) ? 'email' : 'username');

export const plural = (n, one, many) => (n === 1 ? one : many);
