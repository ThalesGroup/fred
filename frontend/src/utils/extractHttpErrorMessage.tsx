export function extractHttpErrorMessage(error: any): string {
  let httpErrorMsg = 'Unknown error';
  if (error.status) {
    if (error.status == 502) {
      httpErrorMsg = `Bad Gateway: ${error.status} : the server is down.`;
    } else if (error.status == 404) {
      httpErrorMsg = `Not Found: ${error.status}`;
    } else if (error.status == 401) {
      httpErrorMsg = `Unauthorized: ${error.status}`;
    } else if (error.status == 403) { 
      httpErrorMsg = `Forbidden: ${error.status}`;
    } else if (error.status == 500) { 
      httpErrorMsg = `Internal Server Error: ${error.status}`;
    } else if (error.status == 503) {
      httpErrorMsg = `Service Unavailable: ${error.status}`;
    } else {
      httpErrorMsg = `Unknown error: ${error.status}`;
    }
  }
  if (!error.data) {
    return httpErrorMsg;
  }
  return `HTTP Error: ${httpErrorMsg} - ${error.data?.message || 'Unknown error'}`;
}
