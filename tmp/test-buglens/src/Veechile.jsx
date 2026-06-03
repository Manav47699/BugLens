function Car(props)
{
    const cars = [
        {id : 1001, brand:"Ford"},
        {id : 1002, brand: "BMW"},
        {id : 1003, brand: "Audi"}
    ];
    return(
        <>
            <h1>My Cars</h1>
            <ul>
                {cars.map((car)=> <li key = {car.id}>Hi I am {car.brand}</li>)}
            </ul>
        </>
    );
}
export default Car;