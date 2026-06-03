import { useState } from "react";

function Myform()
{
    const [inputs,setInputs] = useState({
        FirstName : "John",
        LastName : "Doe"
    });

    function handlechange(e){
        const name = e.target.name;
        const value = e.target.value;
        setInputs(values => ({...inputs,[name]:value}));
    }


    return(
        <form>
            <label>First Name:
                <input type = "text" name = "FirstName"
                onChange = {handlechange}/>
            </label>
            <label>Last Name:
                <input type = "text" name = "LastName" onChange = {handlechange} />
            </label>
            <p>First Name : {inputs.FirstName}</p>
            <p>Last Name : {inputs.LastName}</p>
        </form>
    );
}

export default Myform;